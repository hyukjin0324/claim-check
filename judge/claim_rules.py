"""F8 서류 누락 검사, F9 중복 제출 검사."""
from .checks import make_issue

RECEIPT_TYPES = ("receipt", "simple_receipt", "pharmacy_receipt")


def _receipt_identity(doc, values):
    """같은 서류로 볼 기준. 영수증 번호가 있으면 번호만 쓴다. 값이 모자라면 None."""
    if values.get("receipt_no"):
        return values["receipt_no"]
    start = values.get("visit_start") or values.get("issue_date")
    parts = (values.get("provider_name"), start, values.get("patient_name"), values.get("paid_total"))
    return None if any(p is None for p in parts) else ("auto",) + parts + (values.get("visit_end"),)


def _unique_receipts(documents, all_values):
    seen, unique, duplicates = {}, [], []
    for doc in documents:
        if doc["type"] not in RECEIPT_TYPES:
            continue
        key = _receipt_identity(doc, all_values[doc["doc_id"]])
        if key is not None and key in seen:
            duplicates.append((seen[key], doc))
            continue
        if key is not None:
            seen[key] = doc
        unique.append(doc)
    return unique, duplicates


def duplicate_check(documents, all_values, previous=()):
    issues = []
    _, duplicates = _unique_receipts(documents, all_values)
    for first, second in duplicates:
        amount = all_values[second["doc_id"]].get("patient_total")
        issues.append(make_issue("DUPLICATE", None, None, "같은 영수증이 두 번 들어왔어요.", amount, [first["doc_id"], second["doc_id"]], ["receipt_no"],
                                 "같은 영수증이 중복 제출되어 한 장만 접수합니다."))
    receipts = [d for d in documents if d["type"] in RECEIPT_TYPES]
    unknown = [d["doc_id"] for d in receipts if _receipt_identity(d, all_values[d["doc_id"]]) is None]
    if len(receipts) > 1 and unknown:
        issues.append(make_issue("NEEDS_REVIEW", "F9", "UNVERIFIED_INPUT", "값이 확정되지 않아 중복 여부를 판단하지 못했어요.", None, unknown))
    for doc in receipts:
        number = all_values[doc["doc_id"]].get("receipt_no")
        if number and number in previous:
            issues.append(make_issue("DUPLICATE", None, None, f"이전 청구에 있던 영수증 번호({number})예요.", all_values[doc["doc_id"]].get("patient_total"),
                                     [doc["doc_id"]], ["receipt_no"], "이전에 청구한 영수증과 같아 확인이 필요합니다."))
    return issues


def required_docs_check(claim_type, documents, all_values, all_fields, config):
    issues = []
    has = lambda *kinds: any(d["type"] in kinds for d in documents)
    ids = [d["doc_id"] for d in documents]
    if not has(*RECEIPT_TYPES):
        issues.append(make_issue("DOC_MISSING", "D1", None, "진료비 또는 약제비 영수증이 없어요.", None, ids, [],
                                 "진료비 계산서·영수증을 보내 주세요."))
        return issues

    unique, _ = _unique_receipts(documents, all_values)
    totals = [all_values[d["doc_id"]].get("patient_total") for d in unique]
    total = None if any(t is None for t in totals) else sum(totals)
    receipt_ids = [d["doc_id"] for d in unique]
    # 잘린 영수증은 CROPPED 이슈 하나로 넘겨서, 금액을 모른다는 이슈를 또 만들지 않는다.
    cropped = any("CROPPED" in d.get("flags", []) for d in unique)
    if total is None and cropped:
        return issues

    if claim_type == "outpatient":
        departments = {all_values[d["doc_id"]].get("department") for d in unique} - {None}
        special = departments & set(config["no_simplified_departments"])
        evidence = has("diagnosis", "visit_cert")
        if total is None:
            issues.append(make_issue("NEEDS_REVIEW", "D2", "UNVERIFIED_INPUT", "청구 금액이 확정되지 않아 필요 서류를 판단하지 못했어요.", None, receipt_ids, ["patient_total"]))
        else:
            if total > config["outpatient_prescription_over"] and not special:
                prescriptions = [d for d in documents if d["type"] == "prescription"]
                unresolved = any(f["doc_id"] == d["doc_id"] and f["key"] == "disease_code" and f["status"] == "needs_review"
                                 for d in prescriptions for f in all_fields[d["doc_id"]])
                coded = any(all_values[d["doc_id"]].get("disease_code") for d in prescriptions)
                if unresolved and not coded:
                    issues.append(make_issue("NEEDS_REVIEW", "D2", "UNVERIFIED_INPUT", "처방전의 질병분류기호를 확정하지 못했어요.", None, [d["doc_id"] for d in prescriptions], ["disease_code"]))
                elif not coded:
                    message = "처방전에 질병분류기호가 없어요." if prescriptions else "청구 금액이 3만 원을 넘는데 질병분류기호가 적힌 처방전이 없어요."
                    issues.append(make_issue("DOC_MISSING", "D2", None, message, None, receipt_ids, ["disease_code"], "질병분류기호가 적힌 처방전을 추가로 보내 주세요."))
            if total > config["outpatient_extra_evidence_over"] and not evidence and not special:
                issues.append(make_issue("NEEDS_REVIEW", "D3", None, "10만 원 초과 통원이라 추가 증빙이 필요할 수 있어요.", None, receipt_ids, [], None))
        if special and not evidence:
            issues.append(make_issue("NEEDS_REVIEW", "D4", None, f"{', '.join(sorted(special))} 통원은 간소화 기준을 적용하지 않아 추가 증빙이 필요할 수 있어요.", None, receipt_ids, ["department"], None))

    if claim_type == "inpatient":
        missing = []
        if not has("itemized_bill"):
            missing.append("진료비 세부산정내역서")
        certificates = [d for d in documents if d["type"] == "visit_cert" and all_values[d["doc_id"]].get("disease_name")]
        small = total is not None and total <= config["inpatient_certificate_up_to"]
        name_unresolved = any(f["key"] == "disease_name" and f["status"] == "needs_review"
                              for d in documents if d["type"] == "visit_cert" for f in all_fields[d["doc_id"]])
        if not has("diagnosis") and not (small and certificates):
            if has("visit_cert") and (total is None or (small and name_unresolved)):
                issues.append(make_issue("NEEDS_REVIEW", "D5", "UNVERIFIED_INPUT", "금액이나 진단명이 확정되지 않아 확인서로 대체할 수 있는지 판단하지 못했어요.", None, receipt_ids, ["patient_total"]))
            else:
                missing.append("진단서" if not small else "진단서 또는 진단명이 있는 확인서")
        if missing:
            issues.append(make_issue("DOC_MISSING", "D5", None, f"입원 청구에 필요한 {', '.join(missing)}가 없어요.", None, receipt_ids, [], f"{', '.join(missing)}를 추가로 보내 주세요."))
    return issues
