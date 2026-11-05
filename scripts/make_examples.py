"""팀이 참고할 예시와 ②가 나오기 전에 쓸 가짜 추출 결과를 만든다.

실행: python3 scripts/make_examples.py
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from judge import judge_claim  # noqa: E402
from judge.perfect import answer_to_extract  # noqa: E402


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_answer(number):
    return json.loads((ROOT / "answers" / f"case_{number:02d}.json").read_text(encoding="utf-8"))


def with_evidence(extract):
    """실제 추출 결과처럼 근거 칸과 신뢰도를 채운다. 값은 가짜다."""
    for doc in extract["documents"]:
        for number, field in enumerate(doc["fields"]):
            field["path_a"].update(block_id=f"{doc['doc_id']}_cell_{number}", ocr_confidence=0.97)
            value = field["path_b"]["value"]
            field["path_b"]["quote"] = None if value is None else f"{value:,}" if isinstance(value, int) else str(value)
    return extract


def set_reads(extract, doc_id, key, a, b):
    for doc in extract["documents"]:
        if doc["doc_id"] == doc_id:
            field = next(f for f in doc["fields"] if f["key"] == key)
            field["path_a"]["value"], field["path_b"]["value"] = a, b


def main():
    answer = load_answer(7)
    extract = with_evidence(answer_to_extract(answer))
    write(ROOT / "examples" / "case_07.answer.json", answer)
    write(ROOT / "examples" / "case_07.extract.json", extract)
    write(ROOT / "examples" / "case_07.judge.json", judge_claim(extract))

    fakes = ROOT / "fixtures"
    write(fakes / "fake_agree.extract.json", extract)

    # 경로 B가 본인부담금을 잘못 읽었고, C1로 경로 A를 고른다.
    picked = copy.deepcopy(extract)
    picked["claim_id"] = "fake_checksum"
    set_reads(picked, "d1", "copay_total", 4200, 4800)
    write(fakes / "fake_checksum.extract.json", picked)

    # 공단부담금이 쓰이는 C1, C2의 다른 항도 함께 흔들려 고를 수 없다.
    unstable = copy.deepcopy(extract)
    unstable["claim_id"] = "fake_unstable"
    set_reads(unstable, "d1", "insurer_total", 9800, 9300)
    set_reads(unstable, "d1", "bill_total", 67000, 66500)
    set_reads(unstable, "d1", "insurer_grand_total", 9800, 9300)
    write(fakes / "fake_unstable.extract.json", unstable)


if __name__ == "__main__":
    main()
