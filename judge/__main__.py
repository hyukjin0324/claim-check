"""추출 결과 파일 하나를 판정한다. 실행: python3 -m judge outputs/extract/case_01.json -o outputs/judge/case_01.json"""
import argparse
import json
import sys
from pathlib import Path

from .pipeline import judge_claim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("extract")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()
    result = judge_claim(json.loads(Path(args.extract).read_text(encoding="utf-8")))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
