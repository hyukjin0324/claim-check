"""정답 값을 넣고 판정 규칙만 채점한다. OCR과 추출의 정확도는 재지 않는다.

실행: python3 scripts/score_rules.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from judge import judge_claim  # noqa: E402
from judge.perfect import answer_to_extract  # noqa: E402


def issue_ids(issues):
    return {(i["cause"], i.get("rule"), i.get("review_code")) for i in issues}


def score_case(answer):
    extract = answer_to_extract(answer)
    result = judge_claim(extract)
    doc_ids = {d["file_name"]: d["doc_id"] for d in extract["documents"]}
    confirmed = {(f["doc_id"], f["key"]): f["value"] for f in result["fields"] if f["status"] == "confirmed"}
    wrong = [f["key"] for f in answer["fields"]
             if (doc_ids[f["file_name"]], f["key"]) in confirmed and confirmed[(doc_ids[f["file_name"]], f["key"])] != f["value"]]
    expected, found = issue_ids(answer["issues"]), issue_ids(result["issues"])
    amounts = {i["rule"]: i["amount_diff"] for i in result["issues"]}
    wrong_amounts = [i["rule"] for i in answer["issues"] if i.get("amount_diff") is not None and amounts.get(i["rule"]) != i["amount_diff"]]
    return {
        "case_id": answer["case_id"], "expected": expected, "found": found,
        "conclusion_ok": result["conclusion"] == answer["conclusion"],
        "conclusion": result["conclusion"], "wrong_values": wrong, "wrong_amounts": wrong_amounts,
    }


def load_answers():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "answers").glob("case_*.json"))]


def main():
    scores = [score_case(a) for a in load_answers()]
    hit = sum(len(s["expected"] & s["found"]) for s in scores)
    expected = sum(len(s["expected"]) for s in scores)
    found = sum(len(s["found"]) for s in scores)
    conclusions = sum(s["conclusion_ok"] for s in scores)
    print(f"결론 {conclusions}/{len(scores)}, 이슈 재현 {hit}/{expected}, 이슈 정밀 {hit}/{found}")
    failed = [s for s in scores if not s["conclusion_ok"] or s["expected"] != s["found"] or s["wrong_values"] or s["wrong_amounts"]]
    for s in failed:
        print(f"{s['case_id']}: 결론 {s['conclusion']}, 빠짐 {s['expected'] - s['found']}, 더 나옴 {s['found'] - s['expected']}, 값 {s['wrong_values']}, 금액 {s['wrong_amounts']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
