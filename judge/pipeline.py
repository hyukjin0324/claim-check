"""F6~F10을 차례로 돌려 판정 결과를 만든다."""
import json
from pathlib import Path

from .checks import cross_checks, itemized_checks, make_issue, row_sum_checks
from .claim_rules import duplicate_check, required_docs_check
from .confirm import confirm_document, confirmed_values

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "config" / "required_docs.json").read_text(encoding="utf-8"))
READ_ERROR_CODES = {"READ_CONFLICT", "UNSTABLE_BASE", "AMBIGUOUS_VALUE", "LOW_OCR"}
SUPPLEMENT_CAUSES = {"DOC_MISMATCH", "DOC_MISSING", "DUPLICATE"}
UNKNOWN_DOC_CONFIDENCE = 0.7
REASONS = {
    "READ_CONFLICT": "두 방법이 다르게 읽었고 검산으로도 고르지 못했어요.",
    "UNSTABLE_BASE": "검산에 쓸 다른 값이 흔들려 판단하지 못했어요.",
    "AMBIGUOUS_VALUE": "두 값이 모두 검산식을 통과해 고르지 못했어요.",
    "LOW_OCR": "이 칸을 잘 읽지 못했어요.",
    "MISSING_FIELD": "필요한 값을 찾지 못했어요.",
}


def field_issues(doc, fields):
    issues = []
    for field in fields:
        code = field["review_code"]
        if field["status"] != "needs_review" or code in ("CROPPED", "INTERNAL_MISMATCH"):
            continue
        cause = "READ_ERROR" if code in READ_ERROR_CODES else "NEEDS_REVIEW"
        issues.append(make_issue(cause, None, code, f"{field['key']}: {REASONS[code]}", None, [doc["doc_id"]], [field["key"]]))
    return issues


def broken_equation_issues(doc, checks):
    """두 경로가 같게 읽었는데 깨진 검산식. 식 하나에 이슈 하나만 만든다."""
    return [make_issue("NEEDS_REVIEW", c["rule"], "INTERNAL_MISMATCH", f"{c['rule']} 검산식이 {abs(c['difference']):,}원 맞지 않아요.",
                       abs(c["difference"]), [doc["doc_id"]], c["terms"]) for c in checks if c["result"] == "fail"]


def doc_flag_issues(doc):
    issues = []
    confidence = doc.get("type_confidence")
    if "CROPPED" in doc.get("flags", []):
        issues.append(make_issue("NEEDS_REVIEW", None, "CROPPED", "문서 일부가 잘렸어요.", None, [doc["doc_id"]]))
    if "UNKNOWN_DOC" in doc.get("flags", []) or (confidence is not None and confidence < UNKNOWN_DOC_CONFIDENCE):
        issues.append(make_issue("NEEDS_REVIEW", None, "UNKNOWN_DOC", "어떤 서류인지 확실하지 않아요.", None, [doc["doc_id"]]))
    return issues


def conclude(issues):
    causes = {i["cause"] for i in issues}
    if not causes:
        return "proceed"
    return "needs_review" if causes - SUPPLEMENT_CAUSES else "request_supplement"


def judge_claim(extract, previous_receipts=(), config=None):
    config = config or CONFIG
    documents = extract["documents"]
    all_fields, all_values, checks, issues = {}, {}, [], []
    for doc in documents:
        fields, doc_checks = confirm_document(doc, config["low_ocr_threshold"])
        all_fields[doc["doc_id"]] = fields
        all_values[doc["doc_id"]] = confirmed_values(fields)
        checks += doc_checks
        issues += doc_flag_issues(doc) + field_issues(doc, fields) + broken_equation_issues(doc, doc_checks)
        for found, found_checks in (row_sum_checks(doc, all_values[doc["doc_id"]], config["row_sum_tolerance"]), itemized_checks(doc, all_values[doc["doc_id"]])):
            issues += found
            checks += found_checks
    found, found_checks = cross_checks(documents, all_values, all_fields)
    issues += found
    checks += found_checks
    issues += required_docs_check(extract["claim_type"], documents, all_values, all_fields, config)
    issues += duplicate_check(documents, all_values, previous_receipts)

    issues.sort(key=lambda i: -(i["amount_diff"] or 0))
    for number, issue in enumerate(issues, 1):
        issue["issue_id"] = f"i{number}"
    return {
        "claim_id": extract["claim_id"],
        "conclusion": conclude(issues),
        "documents": [{"doc_id": d["doc_id"], "file_name": d["file_name"], "type": d["type"], "form_no": d.get("form_no")} for d in documents],
        "fields": [f for doc in documents for f in all_fields[doc["doc_id"]]],
        "checks": checks,
        "issues": issues,
    }
