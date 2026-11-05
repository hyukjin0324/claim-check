"""저장소 규칙을 검사한다. 정답지와 서류의 짝, 올리면 안 되는 파일과 비밀값을 본다.

실행: python3 scripts/check_repo.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKED_PATHS = re.compile(r"^(private/|outputs/.*\.json$|\.env$)")
SECRET = re.compile(r"\bup_[A-Za-z0-9]{20,}\b|\b(?:UPSTAGE_API_KEY)\s*=\s*\S+")
TEXT_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml", ".txt", ".sh", ".swift", ".html", ".example"}


def tracked_files():
    output = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return output.splitlines()


def check_pairs():
    problems = []
    answers = {p.stem: p for p in (ROOT / "answers").glob("case_*.json")}
    folders = {p.name for p in (ROOT / "cases").glob("case_*") if p.is_dir()}
    problems += [f"{name}: 서류 폴더 없음" for name in sorted(set(answers) - folders)]
    problems += [f"{name}: 정답지 없음" for name in sorted(folders - set(answers))]
    for name, path in sorted(answers.items()):
        answer = json.loads(path.read_text(encoding="utf-8"))
        if answer.get("source_type") == "real":
            problems.append(f"{name}: 실제 서류 정답지는 private/에 둔다")
        if name in folders:
            for doc in answer["documents"]:
                if not list((ROOT / "cases" / name).glob(doc["file_name"] + ".*")):
                    problems.append(f"{name}: {doc['file_name']} 이미지 없음")
    return problems


def check_tracked(files):
    problems = [f"{name}: 올리면 안 되는 파일" for name in files if BLOCKED_PATHS.match(name)]
    for name in files:
        path = ROOT / name
        if path.suffix in TEXT_SUFFIXES and path.is_file():
            if SECRET.search(path.read_text(encoding="utf-8", errors="ignore")):
                problems.append(f"{name}: 비밀값으로 보이는 문자열")
    return problems


def main():
    problems = check_pairs() + check_tracked(tracked_files())
    for problem in problems:
        print(problem)
    print("문제", len(problems), "건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
