"""F6 뒤의 참고 검사(S1~S3)와 F7 문서 간 검증."""
import re
from datetime import timedelta

from .values import masked_equal, same_text, to_date, to_int

RECEIPT_TYPES = ("receipt", "simple_receipt", "pharmacy_receipt")
HOSPITAL_TYPES = ("receipt", "simple_receipt", "itemized_bill", "prescription", "diagnosis", "visit_cert")
COLUMNS = (("copay", "copay_total"), ("insurer", "insurer_total"), ("full_copay", "full_copay_total"), ("noncovered", "noncovered_total"))


def make_issue(cause, rule=None, review_code=None, message="", amount=None, doc_ids=(), keys=(), request=None):
    return {"cause": cause, "rule": rule, "review_code": review_code, "message": message, "amount_diff": amount,
            "doc_ids": list(doc_ids), "keys": list(keys), "request_text": request}


def row_sum_checks(doc, values, tolerance):
    """S1. 끝수처리 때문에 다를 수 있어 허용 범위 안이면 통과."""
    issues, checks = [], []
    if doc["type"] not in RECEIPT_TYPES:
        return issues, checks
    for column, total_key in COLUMNS:
        keys = [k for k in values if re.fullmatch(rf"row:.+:{column}", k)]
        if not keys or total_key not in values:
            continue
        difference = sum(values[k] or 0 for k in keys) - values[total_key]
        ok = abs(difference) <= tolerance
        checks.append({"rule": "S1", "doc_id": doc["doc_id"], "column": column, "result": "pass" if ok else "fail", "difference": difference})
        if not ok:
            issues.append(make_issue("NEEDS_REVIEW", "S1", "INTERNAL_MISMATCH", f"{column} 항목 합이 합계와 {abs(difference):,}원 달라요.",
                                     abs(difference), [doc["doc_id"]], [total_key]))
    # 옛 양식은 본인부담금과 공단부담금을 한 칸(요양급여)에 합쳐 적는다.
    covered = [k for k in values if re.fullmatch(r"row:.+:covered", k)]
    if covered and "copay_total" in values and "insurer_total" in values:
        difference = sum(values[k] or 0 for k in covered) - values["copay_total"] - values["insurer_total"]
        ok = abs(difference) <= tolerance
        checks.append({"rule": "S1", "doc_id": doc["doc_id"], "column": "covered", "result": "pass" if ok else "fail", "difference": difference})
        if not ok:
            issues.append(make_issue("NEEDS_REVIEW", "S1", "INTERNAL_MISMATCH", f"요양급여 항목 합이 합계와 {abs(difference):,}원 달라요.",
                                     abs(difference), [doc["doc_id"]], ["copay_total", "insurer_total"]))
    return issues, checks


def itemized_checks(doc, values):
    """S2, S3. 세부내역서 안의 합계 관계."""
    issues, checks = [], []
    if doc["type"] != "itemized_bill":
        return issues, checks
    for column in ("copay", "insurer", "full_copay", "noncovered", "total"):
        line_keys = [k for k in values if re.fullmatch(rf"line:\d+:{column}", k)]
        subtotal, adjustment, grand = (values.get(f"{part}.{column}") for part in ("subtotal", "adjustment", "grand_total"))
        if line_keys and subtotal is not None:
            difference = sum(values[k] or 0 for k in line_keys) - subtotal
            checks.append({"rule": "S2", "doc_id": doc["doc_id"], "column": column, "result": "pass" if not difference else "fail", "difference": difference})
            if difference:
                issues.append(make_issue("NEEDS_REVIEW", "S2", "INTERNAL_MISMATCH", f"세부내역서 {column} 줄 합이 계와 {abs(difference):,}원 달라요.",
                                         abs(difference), [doc["doc_id"]], [f"subtotal.{column}"]))
        if subtotal is not None and grand is not None:
            difference = subtotal + (adjustment or 0) - grand
            checks.append({"rule": "S3", "doc_id": doc["doc_id"], "column": column, "result": "pass" if not difference else "fail", "difference": difference})
            if difference:
                issues.append(make_issue("NEEDS_REVIEW", "S3", "INTERNAL_MISMATCH", f"세부내역서 {column} 계와 조정금액의 합이 합계와 {abs(difference):,}원 달라요.",
                                         abs(difference), [doc["doc_id"]], [f"grand_total.{column}"]))
    return issues, checks


VISIT_COLUMNS = (("total", "bill_total"), ("insurer", "insurer_total"), ("patient_total", "patient_total"))


def visit_dates(values):
    return sorted({m.group(1) for k in values for m in [re.fullmatch(r"visit:(.+):total", k)] if m})


def visit_sum_checks(doc, values):
    """S4. 여러 날을 묶은 내역서의 날짜별 소계 합 = 총합."""
    issues, checks = [], []
    dates = visit_dates(values)
    if doc["type"] != "itemized_bill" or not dates:
        return issues, checks
    for column, grand in (("total", "grand_total.total"), ("insurer", "grand_total.insurer"), ("patient_total", "grand_total.patient_total")):
        parts = [values.get(f"visit:{d}:{column}") for d in dates]
        if grand not in values or any(p is None for p in parts):
            continue
        difference = sum(parts) - values[grand]
        checks.append({"rule": "S4", "doc_id": doc["doc_id"], "column": column, "result": "fail" if difference else "pass", "difference": difference})
        if difference:
            issues.append(make_issue("NEEDS_REVIEW", "S4", "INTERNAL_MISMATCH", f"내역서 날짜별 소계의 합이 총합과 {abs(difference):,}원 달라요.",
                                     abs(difference), [doc["doc_id"]], [grand]))
    return issues, checks


def _visit_checks(doc, receipts, by_id):
    """X7. 여러 날을 묶은 내역서는 날짜별 소계를 그날 영수증과 비교한다."""
    issues, checks = [], []
    values = by_id[doc["doc_id"]]
    by_date = {by_id[r["doc_id"]].get("visit_start"): r for r in receipts}
    for date in visit_dates(values):
        receipt = by_date.get(date)
        if receipt is None:
            issues.append(make_issue("NEEDS_REVIEW", "X7", "UNVERIFIED_INPUT", f"{date} 진료의 영수증이 없어 내역서와 비교하지 못했어요.", values.get(f"visit:{date}:patient_total"),
                                     [doc["doc_id"]], [f"visit:{date}:total"]))
            continue
        base = by_id[receipt["doc_id"]]
        diffs = []
        for column, key in VISIT_COLUMNS:
            left, right = values.get(f"visit:{date}:{column}"), base.get(key)
            if left is None or right is None:
                issues.append(_unverified("X7", f"{date} 내역서 소계 또는 영수증", [receipt["doc_id"], doc["doc_id"]]))
                diffs = None
                break
            if left != right:
                diffs.append(abs(left - right))
        if diffs is None:
            continue
        checks.append({"rule": "X7", "doc_id": doc["doc_id"], "date": date, "result": "fail" if diffs else "pass", "difference": max(diffs) if diffs else 0})
        if diffs:
            issues.append(make_issue("DOC_MISMATCH", "X7", None, f"{date} 내역서 소계와 영수증이 최대 {max(diffs):,}원 달라요.", max(diffs), [receipt["doc_id"], doc["doc_id"]],
                                     [f"visit:{date}:total"], "진료비 내역서와 영수증의 금액을 확인해 재발급해 주세요."))
    return issues, checks


def _unverified(rule, what, doc_ids, keys=()):
    return make_issue("NEEDS_REVIEW", rule, "UNVERIFIED_INPUT", f"{what} 값이 확정되지 않아 비교하지 못했어요.", None, doc_ids, keys)


def _names_match(a, b):
    return same_text(a, b) or masked_equal(a, b)


def _link_itemized(doc, receipts, by_id):
    """세부내역서와 같은 진료의 영수증을 찾는다. 서식에 영수증 번호 칸이 없다."""
    if len(receipts) == 1:
        return receipts[0]
    start = by_id[doc["doc_id"]].get("visit_start")
    matches = [r for r in receipts if by_id[r["doc_id"]].get("visit_start") == start]
    return matches[0] if matches and start is not None else None


def cross_checks(documents, all_values, all_fields):
    """F7. 확정된 값끼리만 서류 사이에서 비교한다."""
    issues, checks = [], []
    receipts = [d for d in documents if d["type"] in ("receipt", "simple_receipt")]
    by_id = {d["doc_id"]: all_values[d["doc_id"]] for d in documents}

    for doc in documents:
        if doc["type"] != "itemized_bill":
            continue
        values = by_id[doc["doc_id"]]
        if visit_dates(values):
            found, found_checks = _visit_checks(doc, receipts, by_id)
            issues += found
            checks += found_checks
            continue
        receipt = _link_itemized(doc, receipts, by_id)
        if receipt is None:
            if receipts:
                issues.append(_unverified("X1", "세부내역서와 연결할 영수증의", [doc["doc_id"]]))
            continue
        base = by_id[receipt["doc_id"]]
        diffs, unverified = [], False
        for column, total_key in COLUMNS:
            left, right = values.get(f"grand_total.{column}"), base.get(total_key)
            if left is None or right is None:
                unverified = True
            elif left != right:
                diffs.append(abs(left - right))
        pair = [receipt["doc_id"], doc["doc_id"]]
        if unverified:
            issues.append(_unverified("X1", "세부내역서 또는 영수증 합계", pair))
            checks.append({"rule": "X1", "doc_id": doc["doc_id"], "result": "skipped", "difference": None})
        else:
            checks.append({"rule": "X1", "doc_id": doc["doc_id"], "result": "fail" if diffs else "pass", "difference": max(diffs) if diffs else 0})
            if diffs:
                issues.append(make_issue("DOC_MISMATCH", "X1", None, f"세부내역서와 영수증의 항목별 합계가 최대 {max(diffs):,}원 달라요.", max(diffs), pair,
                                         ["grand_total"], "진료비 세부산정내역서와 영수증의 금액을 확인해 재발급해 주세요."))
        left, right = values.get("grand_total.total"), base.get("bill_total")
        if left is None or right is None:
            issues.append(_unverified("X2", "세부내역서 또는 영수증 총액", pair))
        else:
            difference = abs(left - right)
            checks.append({"rule": "X2", "doc_id": doc["doc_id"], "result": "fail" if difference else "pass", "difference": difference})
            if difference:
                issues.append(make_issue("DOC_MISMATCH", "X2", None, f"세부내역서 총액과 영수증 진료비 총액이 {difference:,}원 달라요.", difference, pair,
                                         ["grand_total.total", "bill_total"], "진료비 세부산정내역서와 영수증의 금액을 확인해 재발급해 주세요."))

    named = [d for d in documents if d["type"] != "other"]
    names = [(d["doc_id"], by_id[d["doc_id"]].get("patient_name")) for d in named]
    known = [(i, n) for i, n in names if n is not None]
    x3_failed = any(not _names_match(known[0][1], n) for _, n in known[1:]) if known else False
    if x3_failed:
        issues.append(make_issue("DOC_MISMATCH", "X3", None, "서류끼리 환자 이름이 달라요.", None, [i for i, _ in known], ["patient_name"],
                                 "환자 이름이 서류마다 달라 확인이 필요합니다. 올바른 서류를 다시 보내 주세요."))
    elif len(names) > 1 and len(known) < len(names):
        issues.append(_unverified("X3", "환자 이름", [i for i, n in names if n is None], ["patient_name"]))
    if len(names) > 1:
        checks.append({"rule": "X3", "doc_id": None, "result": "fail" if x3_failed else "pass" if len(known) == len(names) else "skipped", "difference": None})

    date_keys = {"itemized_bill": ("visit_start", "visit_end"), "visit_cert": ("visit_start", "visit_end"),
                 "prescription": ("issue_date",), "diagnosis": ("admission_date", "discharge_date")}
    dated = [d for d in documents if d["type"] in date_keys]
    if receipts and dated:
        starts = [to_date(by_id[r["doc_id"]].get("visit_start")) for r in receipts]
        ends = [to_date(by_id[r["doc_id"]].get("visit_end") or by_id[r["doc_id"]].get("visit_start")) for r in receipts]
        # 종료일을 못 읽은 영수증은 시작일로 대신하면 기간이 짧아져 불일치로 잘못 나온다.
        end_unresolved = any(f["key"] == "visit_end" and f["status"] == "needs_review" for r in receipts for f in all_fields[r["doc_id"]])
        if all(starts) and all(ends) and not end_unresolved:
            low, high = min(starts), max(ends)
            failed = False
            for doc in dated:
                for key in date_keys[doc["type"]]:
                    day = to_date(by_id[doc["doc_id"]].get(key))
                    if day and not low <= day <= high:
                        failed = True
                        issues.append(make_issue("DOC_MISMATCH", "X4", None, f"서류 날짜 {day}가 영수증 진료 기간 밖이에요.", None,
                                                 [doc["doc_id"]], [key], "진료일을 확인해 올바른 서류를 다시 보내 주세요."))
                        break
            checks.append({"rule": "X4", "doc_id": None, "result": "fail" if failed else "pass", "difference": None})
        else:
            issues.append(_unverified("X4", "영수증 진료일", [r["doc_id"] for r in receipts], ["visit_start"]))

    hospital = [d for d in documents if d["type"] in HOSPITAL_TYPES]
    providers = [(d["doc_id"], by_id[d["doc_id"]].get("provider_name")) for d in hospital]
    known = [(i, p) for i, p in providers if p]
    if known and any(not same_text(known[0][1], p) for _, p in known[1:]):
        issues.append(make_issue("DOC_MISMATCH", "X5", None, "서류끼리 요양기관이 달라요.", None, [i for i, _ in known], ["provider_name"],
                                 "요양기관이 서류마다 달라 확인이 필요합니다. 올바른 서류를 다시 보내 주세요."))
    elif len(providers) > 1 and len(known) < len(providers):
        issues.append(_unverified("X5", "요양기관", [i for i, p in providers if not p], ["provider_name"]))

    prescriptions = [d for d in documents if d["type"] == "prescription"]
    for pharmacy in (d for d in documents if d["type"] == "pharmacy_receipt"):
        filled = to_date(by_id[pharmacy["doc_id"]].get("issue_date"))
        for prescription in prescriptions:
            issued = to_date(by_id[prescription["doc_id"]].get("issue_date"))
            days = to_int(by_id[prescription["doc_id"]].get("valid_days"))
            pair = [prescription["doc_id"], pharmacy["doc_id"]]
            if filled is None or issued is None or days is None:
                issues.append(_unverified("X6", "처방전 발급일, 사용기간 또는 조제일", pair))
                continue
            ok = issued <= filled <= issued + timedelta(days=days)
            checks.append({"rule": "X6", "doc_id": pharmacy["doc_id"], "result": "pass" if ok else "fail", "difference": None})
            if not ok:
                issues.append(make_issue("DOC_MISMATCH", "X6", None, "약국 조제일이 처방전 사용기간 밖이에요.", None, pair,
                                         ["issue_date"], "처방전과 약제비 영수증의 날짜를 확인해 주세요."))
    return issues, checks
