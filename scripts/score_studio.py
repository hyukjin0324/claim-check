"""Studio 실행 결과를 최종 제출 정답지와 키별로 비교한다.

실행: python3 scripts/score_studio.py <정답지.json> <결과 폴더> [--out 저장할파일.json]

비교 결과는 JSON 파일로 저장한다(기본 outputs/score_studio.json). 맨 앞의 by_key에 키별
일치율과 케이스별 정답·결과가 있고, 화면에는 요약만 나온다.

결과 폴더에는 실행 1번당 파일 1개를 둔다. 파일 이름은 정답지의 file(확장자 뺀 이름)이나
case_id로 시작하고, 반복 실행은 `__`로 구분한다.
    컴학감동_최종제출_set01.txt, 컴학감동_최종제출_set01__run2.txt, A__run3.json

.txt와 .md는 청구_판정 노드의 content를 그대로 저장한 것으로 읽는다. .json은 안에서
`decision:` 줄이 있는 content를 찾는다. 서로 다른 후보가 여럿이면 고르지 않고 실패로 센다.

공식 채점과 같다고 보장하지 않는다. 운영진 답변에서 확인한 것은 정답 값을 내는 노드의
content에서 `키: 값`을 읽고, decision과 목록은 그대로 비교하며, reason 같은 문장은 근거를
본다는 점까지다. 그래서 키 형식과 목록 순서는 엄격하게 보고, reason은 일치율에서 뺀다.

종료 코드: 0 전부 일치, 1 틀린 값·실패한 실행·실행 안 한 케이스 있음, 2 입력 오류.
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "outputs" / "score_studio.json"
TEXT_KEYS = {"reason"}
RESULT_SUFFIXES = {".txt", ".md", ".json"}
AMOUNT_IN_ANSWER = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원")
NUMBER = re.compile(r"\d[\d,]*")


class InputError(Exception):
    """정답지나 결과 폴더가 잘못돼 채점을 시작할 수 없다."""


def nfc(text):
    # macOS에서 만든 파일 이름은 한글 자모가 분리돼 있어 그대로 비교하면 어긋난다.
    return unicodedata.normalize("NFC", str(text))


def load_answer_key(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise InputError(f"정답지를 읽지 못함: {error}") from error
    for name in ("output_keys", "decision_values", "cases"):
        if not data.get(name):
            raise InputError(f"정답지에 {name}이 없음")
    names = {}
    for case in data["cases"]:
        for name in ("case_id", "file", "answer"):
            if name not in case:
                raise InputError(f"정답지 케이스에 {name}이 없음: {case}")
        case_id = case["case_id"]
        absent = [k for k in data["output_keys"] if k not in case["answer"]]
        if absent:
            raise InputError(f"{case_id}: 정답에 키가 없음 {absent}")
        if "decision" in data["output_keys"] and case["answer"]["decision"] not in data["decision_values"]:
            raise InputError(f"{case_id}: decision_values에 없는 정답 {case['answer']['decision']}")
        for name in {nfc(case_id), nfc(Path(case["file"]).stem)}:
            if name in names:
                raise InputError(f"정답지에서 이름이 겹침: {name}")
            names[name] = case_id
    return data


def read_text(path):
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949", errors="replace")


def _has_decision_line(text):
    return any(re.match(r"[\s>*_#`-]*decision[*_`]*\s*[:：]", line) for line in text.splitlines())


def _walk_strings(node, key=None):
    if isinstance(node, dict):
        for name, value in node.items():
            yield from _walk_strings(value, name)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value, key)
    elif isinstance(node, str):
        yield key, node


def extract_content(path):
    """결과 파일에서 판정 노드의 content를 꺼낸다. 돌려주는 값: (content, 실패 이유)."""
    text = read_text(path)
    if Path(path).suffix.lower() != ".json":
        return text, None
    try:
        data = json.loads(text)
    except ValueError as error:
        return None, f"JSON을 읽지 못함: {error}"
    strings = [(key, value) for key, value in _walk_strings(data) if _has_decision_line(value)]
    named = list(dict.fromkeys(value for key, value in strings if key == "content"))
    found = named or list(dict.fromkeys(value for _, value in strings))
    if not found:
        return None, "decision 줄이 있는 값을 찾지 못함"
    if len(found) > 1:
        return None, f"decision 줄이 있는 값이 {len(found)}개라 고르지 않음. 판정 노드의 content만 저장"
    return found[0], None


def parse_content(content, keys):
    """`키: 값` 줄을 읽는다. 돌려주는 값: (키별 값, 형식 경고)."""
    values, seen, warnings = {}, Counter(), []
    lines = content.splitlines()
    for line in lines:
        for key in keys:
            match = re.match(rf"\s*{re.escape(key)}:\s*(.*?)\s*$", line)
            if match:
                seen[key] += 1
                values[key] = match.group(1)
                break
            if re.match(rf"[\s>*_#`-]*{re.escape(key)}[*_`]*\s*[:：]", line):
                warnings.append(f"{key}: 꾸밈이 있어 `키: 값`으로 읽지 않음 ({line.strip()})")
                break
    for key, count in seen.items():
        if count > 1:
            warnings.append(f"{key}: {count}번 나와 값 없음으로 처리")
            del values[key]
    last = next((line.strip() for line in reversed(lines) if line.strip()), None)
    if "decision" in values and last != values["decision"]:
        warnings.append(f"마지막 줄이 decision과 다름 ({last}). 후속 노드 분기가 어긋날 수 있음")
    return values, warnings


def parse_list(text):
    """목록 값을 읽는다. JSON 문자열 배열이 아니면 None."""
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return None


def compare_key(expected, got):
    """돌려주는 값: {match, unordered_match, value, note}."""
    if got is None:
        return {"match": False, "unordered_match": False, "value": None, "note": "값 없음"}
    if isinstance(expected, list):
        value = parse_list(got)
        if value is None:
            return {"match": False, "unordered_match": False, "value": got, "note": "JSON 문자열 배열이 아님"}
        exact = value == expected
        unordered = sorted(value) == sorted(expected)
        note = "순서만 다름" if unordered and not exact else None
        return {"match": exact, "unordered_match": unordered, "value": value, "note": note}
    same = got == str(expected)
    return {"match": same, "unordered_match": same, "value": got, "note": None}


def amount_hint(expected, got):
    """정답 reason의 금액이 결과 reason에 있는지 본다. 근거가 맞다는 뜻은 아니다."""
    amounts = {m.replace(",", "") for m in AMOUNT_IN_ANSWER.findall(str(expected))}
    numbers = {m.replace(",", "") for m in NUMBER.findall(got or "")}
    return {"expected": sorted(amounts), "absent": sorted(amounts - numbers)}


def score_run(case, keys, run, path):
    content, failure = extract_content(path)
    values, warnings = parse_content(content, keys) if content is not None else ({}, [])
    answer = case["answer"]
    scored = {k: compare_key(answer[k], values.get(k)) for k in keys if k not in TEXT_KEYS}
    text = {k: {"expected": answer[k], "value": values.get(k), "amounts": amount_hint(answer[k], values.get(k))}
            for k in keys if k in TEXT_KEYS}
    return {"case_id": case["case_id"], "file": case["file"], "run": run, "source": Path(path).name, "failure": failure,
            "warnings": warnings, "keys": scored, "text_keys": text, "all_match": all(r["match"] for r in scored.values())}


def find_results(folder, cases):
    """결과 파일을 케이스에 짝짓는다. 돌려주는 값: ({case_id: [(run, 경로)]}, 짝 없는 파일)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise InputError(f"결과 폴더가 없음: {folder}")
    names = {}
    for case in cases:
        names[nfc(case["case_id"])] = case["case_id"]
        names[nfc(Path(case["file"]).stem)] = case["case_id"]
    runs, unmatched = {case["case_id"]: [] for case in cases}, []
    for path in sorted(folder.iterdir(), key=lambda p: nfc(p.name)):
        if path.is_dir() or path.name.startswith("."):
            continue
        base, _, label = nfc(path.stem).partition("__")
        if path.suffix.lower() not in RESULT_SUFFIXES or base not in names:
            unmatched.append(path.name)
        else:
            runs[names[base]].append((label or "1", path))
    return runs, unmatched


def _run_order(item):
    digits = re.findall(r"\d+", item[0])
    return (int(digits[-1]) if digits else 0, item[0])


def stability(runs, keys):
    """같은 파일을 여러 번 돌린 결과에서 바뀐 키를 찾는다."""
    rows = []
    by_case = {}
    for run in runs:
        by_case.setdefault(run["case_id"], []).append(run)
    for case_id, items in by_case.items():
        if len(items) < 2:
            continue
        changed = [k for k in keys if k not in TEXT_KEYS
                   and len({json.dumps(r["keys"][k]["value"], ensure_ascii=False) for r in items}) > 1]
        decisions = Counter(str(r["keys"]["decision"]["value"]) for r in items if "decision" in r["keys"])
        rows.append({"case_id": case_id, "runs": len(items), "decisions": dict(decisions), "changed_keys": changed})
    return rows


def score(answer_key, folder):
    cases, keys = answer_key["cases"], answer_key["output_keys"]
    found, unmatched = find_results(folder, cases)
    runs = []
    for case in cases:
        for label, path in sorted(found[case["case_id"]], key=_run_order):
            runs.append(score_run(case, keys, label, path))
    summary = {}
    for key in keys:
        if key in TEXT_KEYS:
            continue
        results = [r["keys"][key] for r in runs]
        summary[key] = {"match": sum(r["match"] for r in results), "unordered_match": sum(r["unordered_match"] for r in results),
                        "total": len(results), "is_list": any(isinstance(c["answer"][key], list) for c in cases)}
    return {
        "output_keys": keys, "case_total": len(cases), "cases_not_run": [c["case_id"] for c in cases if not found[c["case_id"]]],
        "unmatched_files": unmatched, "keys": summary, "runs": runs,
        "run_total": len(runs), "run_all_match": sum(r["all_match"] for r in runs),
        "key_match": sum(s["match"] for s in summary.values()), "key_total": sum(s["total"] for s in summary.values()),
        "stability": stability(runs, keys),
    }


def _rate(match, total):
    return round(match / total, 4) if total else None


def build_report(result, answer_key):
    """키별 비교가 먼저 보이는 저장용 JSON을 만든다."""
    answers = {c["case_id"]: c["answer"] for c in answer_key["cases"]}
    by_key = {}
    for key in result["output_keys"]:
        common = [{"case_id": r["case_id"], "file": r["file"], "run": r["run"], "source": r["source"]} for r in result["runs"]]
        if key in TEXT_KEYS:
            items = [r["text_keys"][key] for r in result["runs"]]
            checked = [i for i in items if i["amounts"]["expected"]]
            by_key[key] = {
                "scored": False, "note": "일치율에서 제외, 사람이 근거를 확인",
                "filled": sum(bool(i["value"]) for i in items), "total": len(items),
                "amount_checked": len(checked), "amount_present": sum(not i["amounts"]["absent"] for i in checked),
                "comparisons": [{**c, "expected": i["expected"], "actual": i["value"], "absent_amounts": i["amounts"]["absent"]}
                                for c, i in zip(common, items)],
            }
            continue
        row = result["keys"][key]
        entry = {"scored": True, "match": row["match"], "total": row["total"], "match_rate": _rate(row["match"], row["total"])}
        if row["is_list"]:
            entry["unordered_match"] = row["unordered_match"]
            entry["unordered_match_rate"] = _rate(row["unordered_match"], row["total"])
        entry["comparisons"] = [{**c, "expected": answers[r["case_id"]][key], "actual": r["keys"][key]["value"],
                                 "match": r["keys"][key]["match"], "note": r["keys"][key]["note"]}
                                for c, r in zip(common, result["runs"])]
        by_key[key] = entry
    return {
        "title": "Studio 실행 결과와 정답지 키별 비교",
        "note": "공식 점수가 아니라 이 폴더의 결과와 정답지를 비교한 건수다.",
        "by_key": by_key,
        "summary": {
            "case_total": result["case_total"], "cases_run": result["case_total"] - len(result["cases_not_run"]),
            "run_total": result["run_total"], "run_all_match": result["run_all_match"],
            "run_all_match_rate": _rate(result["run_all_match"], result["run_total"]),
            "key_match": result["key_match"], "key_total": result["key_total"],
            "key_match_rate": _rate(result["key_match"], result["key_total"]),
        },
        "stability": result["stability"],
        "problems": {
            "cases_not_run": result["cases_not_run"], "unmatched_files": result["unmatched_files"],
            "failed_runs": [{"case_id": r["case_id"], "run": r["run"], "source": r["source"], "failure": r["failure"]}
                            for r in result["runs"] if r["failure"]],
            "format_warnings": [{"case_id": r["case_id"], "run": r["run"], "warning": w}
                                for r in result["runs"] for w in r["warnings"]],
        },
    }


def _ratio(match, total):
    return f"{match}/{total} ({match / total:.1%})" if total else "0/0"


def _short(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)


def print_report(result, answer_key):
    answers = {c["case_id"]: c["answer"] for c in answer_key["cases"]}
    run_total = result["run_total"]
    print(f"케이스 {result['case_total']}건 중 {result['case_total'] - len(result['cases_not_run'])}건 실행, 결과 {run_total}개")
    print("참고: 공식 점수가 아니라 이 폴더의 결과와 정답지를 비교한 건수다.")

    print("\n[키별 일치율]")
    for key, row in result["keys"].items():
        extra = ""
        if row["is_list"] and row["unordered_match"] != row["match"]:
            extra = f"  (순서 무시 {row['unordered_match']}/{row['total']})"
        print(f"  {key:<18} {_ratio(row['match'], row['total'])}{extra}")
    for key in result["output_keys"]:
        if key not in result["keys"]:
            items = [r["text_keys"][key] for r in result["runs"]]
            checked = [i for i in items if i["amounts"]["expected"]]
            present = sum(not i["amounts"]["absent"] for i in checked)
            filled = sum(bool(i["value"]) for i in items)
            print(f"  {key:<18} 일치율에서 제외, 사람이 확인 (값 있음 {filled}/{len(items)}, 정답 금액 포함 {present}/{len(checked)})")
    print(f"  {'키 전체':<16} {_ratio(result['key_match'], result['key_total'])}")
    print(f"  {'실행 전체 일치':<14} {_ratio(result['run_all_match'], run_total)}")

    failed = [r for r in result["runs"] if not r["all_match"]]
    if failed:
        print("\n[틀린 실행]")
    for run in failed:
        print(f"  {run['case_id']} / {run['run']} ({run['source']})")
        if run["failure"]:
            print(f"    실패: {run['failure']}")
        for key, item in run["keys"].items():
            if not item["match"]:
                note = f" [{item['note']}]" if item["note"] else ""
                print(f"    {key}: 정답 {_short(answers[run['case_id']][key])} / 결과 {_short(item['value'])}{note}")

    if result["stability"]:
        print("\n[반복 실행]")
        for row in result["stability"]:
            changed = ", ".join(row["changed_keys"]) or "없음"
            decisions = ", ".join(f"{name} {count}번" for name, count in row["decisions"].items())
            print(f"  {row['case_id']}: {row['runs']}번, {decisions}. 바뀐 키: {changed}")

    warned = [r for r in result["runs"] if r["warnings"]]
    if warned:
        print("\n[형식 경고]")
    for run in warned:
        for warning in run["warnings"]:
            print(f"  {run['case_id']} / {run['run']}: {warning}")

    if result["cases_not_run"]:
        print(f"\n[실행 안 한 케이스] {', '.join(map(str, result['cases_not_run']))}")
    if result["unmatched_files"]:
        print(f"\n[읽지 않은 파일] {', '.join(result['unmatched_files'])}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Studio 실행 결과를 정답지와 키별로 비교한다.")
    parser.add_argument("answer", help="정답지 JSON 파일")
    parser.add_argument("results", help="실행 결과 폴더")
    parser.add_argument("--out", default=DEFAULT_OUT, type=Path, help="비교 결과를 저장할 JSON 파일 (기본 outputs/score_studio.json)")
    args = parser.parse_args(argv)
    try:
        if args.out.resolve().parent == Path(args.results).resolve():
            raise InputError("--out을 결과 폴더 안에 두면 다음 채점 때 결과 파일로 읽힘")
        answer_key = load_answer_key(args.answer)
        result = score(answer_key, args.results)
    except InputError as error:
        print(f"입력 오류: {error}", file=sys.stderr)
        return 2
    print_report(result, answer_key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(build_report(result, answer_key), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n비교 결과 JSON: {args.out}")
    clean = result["run_total"] and result["run_all_match"] == result["run_total"]
    return 0 if clean and not result["cases_not_run"] and not result["unmatched_files"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
