"""F6. 두 경로를 비교하고 검산식으로 값을 확정한다."""
import re

from .values import clean, masked_equal, same_text, to_int

BLANK_IS_ZERO = {
    "full_copay_total", "noncovered_total", "cap_excess", "prepaid", "unpaid",
    "paid_card", "paid_cash_receipt", "paid_cash",
}
MONEY_SUFFIXES = (":covered", ":copay", ":insurer", ":full_copay", ":noncovered", ":total", ":patient_total", ":card", ":cash_receipt", ":cash")
RECEIPT_MONEY = BLANK_IS_ZERO | {"copay_total", "insurer_total", "bill_total", "insurer_grand_total", "patient_total", "due", "paid_total"}

REQUIRED = {
    "receipt": ["patient_name", "provider_name", "visit_start", "copay_total", "insurer_total", "bill_total", "patient_total"],
    "simple_receipt": ["patient_name", "provider_name", "visit_start", "copay_total", "insurer_total", "bill_total", "patient_total"],
    "pharmacy_receipt": ["patient_name", "provider_name", "issue_date", "copay_total", "insurer_total", "bill_total", "patient_total"],
    "itemized_bill": ["patient_name", "provider_name", "visit_start", "grand_total.total"],
    "prescription": ["patient_name", "provider_name", "issue_date"],
    "diagnosis": ["patient_name", "provider_name"],
    "visit_cert": ["patient_name", "provider_name"],
    "payment_cert": ["patient_name", "provider_name"],
}

# 각 식은 {키: 계수}이고 합이 0이어야 한다. 값 확정에 쓰는 식만 둔다.
RECEIPT_EQUATIONS = {
    "C1": {"bill_total": 1, "copay_total": -1, "insurer_total": -1, "full_copay_total": -1, "noncovered_total": -1},
    "C2": {"insurer_grand_total": 1, "insurer_total": -1, "cap_excess": -1},
    "C3": {"patient_total": 1, "copay_total": -1, "cap_excess": 1, "full_copay_total": -1, "noncovered_total": -1},
    "C4": {"due": 1, "patient_total": -1, "prepaid": 1},
    "C5": {"paid_total": 1, "paid_card": -1, "paid_cash_receipt": -1, "paid_cash": -1},
    "C6": {"unpaid": 1, "due": -1, "paid_total": 1},
}
SIMPLE_EQUATIONS = {
    "P1": {"bill_total": 1, "copay_total": -1, "insurer_total": -1, "full_copay_total": -1, "noncovered_total": -1},
    "P2": {"patient_total": 1, "bill_total": -1, "insurer_total": 1},
    "P3": {"paid_total": 1, "paid_card": -1, "paid_cash_receipt": -1, "paid_cash": -1},
}


def holds(name, difference, due=None):
    """검산식 통과 여부. 납부할 금액은 10원이나 100원 단위로 끝수를 버려 적는 서류가 있다."""
    if difference == 0:
        return True
    if name != "C4" or due is None:
        return False
    return (-9 <= difference < 0 and due % 10 == 0) or (-99 <= difference < 0 and due % 100 == 0)


def equations_for(doc, keys):
    kind = doc["type"]
    if kind == "receipt":
        # 서류에 없는 칸을 쓰는 식은 값이 하나도 없을 때 건너뛴다.
        return {name: eq for name, eq in RECEIPT_EQUATIONS.items() if any(k in keys for k in eq)}
    if kind in ("simple_receipt", "pharmacy_receipt"):
        return SIMPLE_EQUATIONS
    if kind == "payment_cert":
        equations = {}
        for n in sorted({m.group(1) for k in keys for m in [re.match(r"line:(\d+):", k)] if m}):
            p = f"line:{n}:"
            equations[f"N1#{n}"] = {p + "total": 1, p + "insurer": -1, p + "copay": -1, p + "full_copay": -1, p + "noncovered": -1}
            equations[f"N2#{n}"] = {p + "patient_total": 1, p + "copay": -1, p + "full_copay": -1, p + "noncovered": -1}
        return equations
    return {}


def is_money(key, doc_type):
    if key in RECEIPT_MONEY or key.endswith(MONEY_SUFFIXES):
        return True
    return key.split(".")[0] in ("subtotal", "adjustment", "grand_total")


def _result(doc_id, key, status, value, basis, review, a, b, block):
    return {"doc_id": doc_id, "key": key, "status": status, "value": value, "basis": basis,
            "review_code": review, "candidates": {"path_a": a, "path_b": b}, "block_id": block}


def _names_compatible(key, a, b):
    return key == "patient_name" and masked_equal(a, b)


def _masked_value(a, b):
    return a if "*" in str(a) else b


def confirm_document(doc, low_ocr_threshold):
    """문서 하나의 필드를 확정하고 (필드 결과, 검산 결과)를 돌려준다."""
    doc_id, kind = doc["doc_id"], doc["type"]
    cropped = "CROPPED" in doc.get("flags", [])
    required = REQUIRED.get(kind, [])
    raw = {}
    for field in doc.get("fields", []):
        key = field["key"]
        a, b = clean(field["path_a"].get("value")), clean(field["path_b"].get("value"))
        money = is_money(key, kind)
        if money:
            a, b = to_int(a), to_int(b)
        # 빈 칸이 0인 칸은 한쪽이 비어 있어도 0으로 읽은 것과 같다.
        if key in BLANK_IS_ZERO and not cropped and (a is None) != (b is None):
            a, b = (0 if a is None else a), (0 if b is None else b)
        raw[key] = dict(a=a, b=b, money=money, conf=field["path_a"].get("ocr_confidence"),
                        block=field["path_a"].get("block_id"))
    for key in required:
        raw.setdefault(key, dict(a=None, b=None, money=is_money(key, kind), conf=None, block=None))
    equations = equations_for(doc, raw)
    for equation in equations.values():
        for key in equation:
            raw.setdefault(key, dict(a=None, b=None, money=True, conf=None, block=None))

    results, stable, pending = {}, {}, []
    for key, r in raw.items():
        a, b = r["a"], r["b"]
        if a is None and b is None:
            if key in BLANK_IS_ZERO and not cropped:
                stable[key] = 0
                results[key] = _result(doc_id, key, "confirmed", 0, {"type": "blank_zero"}, None, a, b, r["block"])
            elif key in required or (cropped and any(key in eq for eq in equations.values())):
                results[key] = _result(doc_id, key, "needs_review", None, None, "CROPPED" if cropped else "MISSING_FIELD", a, b, r["block"])
            else:
                results[key] = _result(doc_id, key, "absent", None, None, None, a, b, r["block"])
        elif a is not None and b is not None and (a == b or (not r["money"] and same_text(a, b))):
            stable[key] = a
        elif a is not None and b is not None and _names_compatible(key, a, b):
            stable[key] = _masked_value(a, b)
            results[key] = _result(doc_id, key, "confirmed", stable[key], {"type": "masked_agree"}, None, a, b, r["block"])
        else:
            pending.append(key)

    def usable(key):
        """key를 포함하고, 나머지 항이 모두 정해진 식."""
        return {name: eq for name, eq in equations.items()
                if key in eq and all(k == key or k in stable for k in eq)}

    def passes(key, value, eqs):
        due = value if key == "due" else stable.get("due")
        return all(holds(name, sum(c * (value if k == key else stable[k]) for k, c in eq.items()), due) for name, eq in eqs.items())

    def winners(key, eqs):
        candidates = [v for v in (raw[key]["a"], raw[key]["b"]) if v is not None]
        return list(dict.fromkeys(v for v in candidates if passes(key, v, eqs)))

    # 값을 고를 수 있는 칸을 하나씩 정하고, 정해진 값은 다음 식의 기준으로 쓴다.
    changed = True
    while changed:
        changed = False
        for key in list(pending):
            eqs = usable(key)
            if eqs and raw[key]["money"] and len(winners(key, eqs)) == 1:
                r = raw[key]
                stable[key] = winners(key, eqs)[0]
                results[key] = _result(doc_id, key, "confirmed", stable[key], {"type": "checksum", "rules": sorted(eqs)}, None, r["a"], r["b"], r["block"])
                pending.remove(key)
                changed = True

    for key in pending:
        r = raw[key]
        eqs = usable(key)
        related = [eq for eq in equations.values() if key in eq]
        if r["money"] and eqs and len(winners(key, eqs)) > 1:
            code = "AMBIGUOUS_VALUE"
        elif any(k != key and k in pending for eq in related for k in eq) and not eqs:
            code = "UNSTABLE_BASE"
        else:
            code = "READ_CONFLICT"
        if cropped and (r["a"] is None or r["b"] is None):
            code = "CROPPED"
        results[key] = _result(doc_id, key, "needs_review", None, None, code, r["a"], r["b"], r["block"])

    # 두 경로가 같게 읽은 값은 관련 검산식을 통과해야 확정한다.
    checks, broken = [], set()
    for name, equation in equations.items():
        terms = sorted(equation)
        if not all(k in stable for k in equation):
            checks.append({"rule": name, "doc_id": doc_id, "result": "skipped", "difference": None, "terms": terms})
            continue
        difference = sum(c * stable[k] for k, c in equation.items())
        checks.append({"rule": name, "doc_id": doc_id, "result": "pass" if holds(name, difference, stable.get("due")) else "fail", "difference": difference, "terms": terms})
        if not holds(name, difference, stable.get("due")):
            broken |= {k for k in equation if not (k in results and results[k]["basis"] and results[k]["basis"]["type"] == "blank_zero")}

    for key, value in stable.items():
        r = raw[key]
        if key in broken:
            results[key] = _result(doc_id, key, "needs_review", None, None, "INTERNAL_MISMATCH", r["a"], r["b"], r["block"])
            continue
        if key not in results:
            rules = sorted(n for n, eq in equations.items() if key in eq and all(k in stable for k in eq))
            results[key] = _result(doc_id, key, "confirmed", value, {"type": "agree", "rules": rules}, None, r["a"], r["b"], r["block"])
        # 신뢰도가 낮은 칸에서 나온 값은 검산을 통과해도 확정하지 않는다.
        if results[key]["basis"]["type"] != "blank_zero" and r["conf"] is not None and r["conf"] < low_ocr_threshold and value == r["a"]:
            results[key] = _result(doc_id, key, "needs_review", None, None, "LOW_OCR", r["a"], r["b"], r["block"])

    return [results[k] for k in raw], checks


def confirmed_values(field_results):
    return {f["key"]: f["value"] for f in field_results if f["status"] == "confirmed"}
