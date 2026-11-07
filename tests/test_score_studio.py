"""Studio 결과 채점 스크립트 테스트. 값은 모두 가상이다."""
import contextlib
import io
import json
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from score_studio import InputError, amount_hint, compare_key, load_answer_key, main, parse_content, score  # noqa: E402

KEYS = ["patient_name", "provider_name", "decision", "cause", "reason", "missing_documents", "mismatches"]


def answer(name, decision, cause, reason, missing=(), mismatches=()):
    return {"patient_name": name, "provider_name": "가상의원", "decision": decision, "cause": cause, "reason": reason,
            "missing_documents": list(missing), "mismatches": list(mismatches)}


ANSWER_KEY = {
    "task": "청구 서류 검증", "unit": "케이스", "output_keys": KEYS,
    "decision_values": ["심사 진행", "보완 요청", "검토 필요"],
    "cases": [
        {"case_id": "A", "file": "팀_set01.pdf", "documents": ["영수증"],
         "answer": answer("김가온", "심사 진행", "없음", "환자부담 총액 4,200원의 3만 원 이하 통원")},
        {"case_id": "D", "file": "팀_set04.pdf", "documents": ["영수증", "세부내역서"],
         "answer": answer("황도현", "보완 요청", "서류 불일치", "비급여 합계가 108,000원으로 영수증 150,000원보다 적음",
                          mismatches=["비급여 합계", "진료비 총액"])},
    ],
}


def content(values, last=None):
    lines = [f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v}" for k, v in values.items()]
    return "\n".join(lines + [last if last is not None else values["decision"]])


def right(case_id):
    return next(c["answer"] for c in ANSWER_KEY["cases"] if c["case_id"] == case_id)


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / "results"
        self.folder.mkdir()
        self.out_path = Path(temp.name) / "report" / "score.json"
        self.key_path = Path(temp.name) / "answer.json"
        self.key_path.write_text(json.dumps(ANSWER_KEY, ensure_ascii=False), encoding="utf-8")

    def save(self, name, text):
        (self.folder / name).write_text(text, encoding="utf-8")

    def result(self):
        return score(ANSWER_KEY, self.folder)

    def exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = main([str(self.key_path), str(self.folder), "--out", str(self.out_path)])
        self.output = out.getvalue()
        return code


class ScoreTest(Base):
    def test_all_match(self):
        self.save("팀_set01.txt", content(right("A")))
        self.save("D.md", content(right("D")))
        result = self.result()
        self.assertEqual((result["key_match"], result["key_total"]), (12, 12))
        self.assertEqual(result["run_all_match"], 2)
        self.assertEqual(self.exit_code(), 0)

    def test_counts_each_key(self):
        self.save("A.txt", content({**right("A"), "decision": "보완 요청"}, last="보완 요청"))
        self.save("D.txt", content(right("D")))
        result = self.result()
        self.assertEqual(result["keys"]["decision"]["match"], 1)
        self.assertEqual(result["keys"]["cause"]["match"], 2)
        self.assertEqual(result["run_all_match"], 1)
        self.assertEqual(self.exit_code(), 1)
        self.assertIn("decision: 정답 심사 진행 / 결과 보완 요청", self.output)

    def test_reason_is_not_in_match_rate(self):
        self.save("A.txt", content({**right("A"), "reason": "전혀 다른 문장"}))
        self.save("D.txt", content(right("D")))
        result = self.result()
        self.assertNotIn("reason", result["keys"])
        self.assertEqual(result["run_all_match"], 2)
        self.assertEqual(result["runs"][0]["text_keys"]["reason"]["amounts"]["absent"], ["4200"])

    def test_case_not_run_is_reported_not_counted_wrong(self):
        self.save("A.txt", content(right("A")))
        result = self.result()
        self.assertEqual(result["cases_not_run"], ["D"])
        self.assertEqual(result["key_total"], 6)
        self.assertEqual(self.exit_code(), 1)
        self.assertIn("[실행 안 한 케이스] D", self.output)

    def test_unmatched_file_is_reported(self):
        self.save("A.txt", content(right("A")))
        self.save("D.txt", content(right("D")))
        self.save("다른세트.txt", content(right("A")))
        self.assertEqual(self.result()["unmatched_files"], ["다른세트.txt"])
        self.assertEqual(self.exit_code(), 1)

    def test_nfd_file_name_matches(self):
        self.save(unicodedata.normalize("NFD", "팀_set01") + ".txt", content(right("A")))
        self.assertNotIn("A", self.result()["cases_not_run"])

    def test_cp949_file(self):
        (self.folder / "A.txt").write_bytes(content(right("A")).encode("cp949"))
        self.assertTrue(self.result()["runs"][0]["all_match"])

    def test_no_results(self):
        self.assertEqual(self.exit_code(), 1)


class ReportFileTest(Base):
    def report(self):
        self.exit_code()
        return json.loads(self.out_path.read_text(encoding="utf-8"))

    def test_by_key_comes_first_with_rate_and_values(self):
        self.save("A.txt", content({**right("A"), "decision": "보완 요청"}, last="보완 요청"))
        self.save("D.txt", content(right("D")))
        report = self.report()
        self.assertEqual(list(report)[2], "by_key")
        self.assertEqual(list(report["by_key"]), KEYS)
        decision = report["by_key"]["decision"]
        self.assertEqual((decision["match"], decision["total"], decision["match_rate"]), (1, 2, 0.5))
        first = decision["comparisons"][0]
        self.assertEqual((first["case_id"], first["expected"], first["actual"], first["match"]), ("A", "심사 진행", "보완 요청", False))

    def test_list_key_has_unordered_rate(self):
        self.save("D.txt", content({**right("D"), "mismatches": ["진료비 총액", "비급여 합계"]}))
        mismatches = self.report()["by_key"]["mismatches"]
        self.assertEqual((mismatches["match_rate"], mismatches["unordered_match_rate"]), (0.0, 1.0))
        self.assertEqual(mismatches["comparisons"][0]["note"], "순서만 다름")
        self.assertNotIn("unordered_match", self.report()["by_key"]["decision"])

    def test_reason_is_not_scored(self):
        self.save("A.txt", content({**right("A"), "reason": "다른 문장"}))
        reason = self.report()["by_key"]["reason"]
        self.assertFalse(reason["scored"])
        self.assertNotIn("match_rate", reason)
        self.assertEqual(reason["comparisons"][0]["absent_amounts"], ["4200"])

    def test_problems_are_listed(self):
        self.save("A.json", "{깨진")
        self.save("메모.txt", "결과 아님")
        problems = self.report()["problems"]
        self.assertEqual(problems["cases_not_run"], ["D"])
        self.assertEqual(problems["unmatched_files"], ["메모.txt"])
        self.assertIn("JSON", problems["failed_runs"][0]["failure"])

    def test_no_runs_gives_empty_rate(self):
        self.assertIsNone(self.report()["by_key"]["decision"]["match_rate"])

    def test_out_inside_results_folder_is_refused(self):
        self.out_path = self.folder / "score.json"
        self.assertEqual(self.exit_code(), 2)
        self.assertFalse(self.out_path.exists())


class JsonResultTest(Base):
    def test_finds_judge_content_among_nodes(self):
        data = {"nodes": [{"name": "청구_판정", "content": content(right("A"))}, {"name": "보완_요청_문구", "content": "안내문"}]}
        self.save("A.json", json.dumps(data, ensure_ascii=False))
        self.assertTrue(self.result()["runs"][0]["all_match"])

    def test_two_candidates_fail_instead_of_guessing(self):
        data = {"nodes": [{"content": content(right("A"))}, {"content": content(right("D"))}]}
        self.save("A.json", json.dumps(data, ensure_ascii=False))
        run = self.result()["runs"][0]
        self.assertFalse(run["all_match"])
        self.assertIn("고르지 않음", run["failure"])

    def test_broken_json_fails(self):
        self.save("A.json", "{깨진")
        run = self.result()["runs"][0]
        self.assertFalse(run["all_match"])
        self.assertIn("JSON", run["failure"])


class RepeatTest(Base):
    def test_reports_changed_keys(self):
        self.save("A.txt", content(right("A")))
        self.save("A__run2.txt", content(right("A")))
        self.save("A__run10.txt", content({**right("A"), "decision": "검토 필요"}, last="검토 필요"))
        result = self.result()
        self.assertEqual([r["run"] for r in result["runs"]], ["1", "run2", "run10"])
        row = result["stability"][0]
        self.assertEqual(row["decisions"], {"심사 진행": 2, "검토 필요": 1})
        self.assertEqual(row["changed_keys"], ["decision"])
        self.assertEqual(result["keys"]["decision"]["total"], 3)

    def test_reason_change_is_not_instability(self):
        self.save("A.txt", content(right("A")))
        self.save("A__run2.txt", content({**right("A"), "reason": "표현만 바뀜 4,200원"}))
        self.assertEqual(self.result()["stability"][0]["changed_keys"], [])


class ParseTest(unittest.TestCase):
    def test_decorated_key_is_not_read(self):
        values, warnings = parse_content("**decision**: 심사 진행\n심사 진행", ["decision"])
        self.assertEqual(values, {})
        self.assertIn("꾸밈", warnings[0])

    def test_fullwidth_colon_is_not_read(self):
        values, warnings = parse_content("decision：심사 진행", ["decision"])
        self.assertEqual(values, {})
        self.assertTrue(warnings)

    def test_repeated_key_has_no_value(self):
        values, warnings = parse_content("decision: 심사 진행\ndecision: 보완 요청\n보완 요청", ["decision"])
        self.assertEqual(values, {})
        self.assertIn("2번", warnings[0])

    def test_warns_when_last_line_differs(self):
        _, warnings = parse_content("decision: 심사 진행\n보완 요청", ["decision"])
        self.assertIn("마지막 줄", warnings[0])

    def test_value_may_contain_colon(self):
        values, _ = parse_content("reason: 합계: 4,200원", ["reason"])
        self.assertEqual(values["reason"], "합계: 4,200원")


class CompareTest(unittest.TestCase):
    def test_list_order_is_reported_separately(self):
        item = compare_key(["비급여 합계", "진료비 총액"], '["진료비 총액", "비급여 합계"]')
        self.assertFalse(item["match"])
        self.assertTrue(item["unordered_match"])
        self.assertEqual(item["note"], "순서만 다름")

    def test_list_must_be_json_array(self):
        for text in ("['처방전']", "처방전", '{"a": "b"}', "[1]"):
            item = compare_key(["처방전"], text)
            self.assertFalse(item["match"], text)
            self.assertFalse(item["unordered_match"], text)

    def test_duplicate_in_list_is_wrong(self):
        self.assertFalse(compare_key(["처방전"], '["처방전", "처방전"]')["unordered_match"])

    def test_text_is_compared_as_is(self):
        self.assertFalse(compare_key("가상내과의원", "가상 내과의원")["match"])

    def test_amount_hint_does_not_match_inside_a_number(self):
        self.assertEqual(amount_hint("4,200원", "54,200원")["absent"], ["4200"])
        self.assertEqual(amount_hint("4,200원", "4200원")["absent"], [])
        self.assertEqual(amount_hint("3만 원 이하", "무관")["expected"], [])


class AnswerKeyTest(Base):
    def write(self, data):
        self.key_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_missing_key_in_answer(self):
        broken = json.loads(json.dumps(ANSWER_KEY))
        del broken["cases"][0]["answer"]["cause"]
        self.write(broken)
        with self.assertRaises(InputError):
            load_answer_key(self.key_path)
        self.assertEqual(self.exit_code(), 2)

    def test_unknown_decision(self):
        broken = json.loads(json.dumps(ANSWER_KEY))
        broken["cases"][0]["answer"]["decision"] = "승인"
        self.write(broken)
        with self.assertRaises(InputError):
            load_answer_key(self.key_path)

    def test_duplicate_file(self):
        broken = json.loads(json.dumps(ANSWER_KEY))
        broken["cases"][1]["file"] = broken["cases"][0]["file"]
        self.write(broken)
        with self.assertRaises(InputError):
            load_answer_key(self.key_path)

    def test_missing_results_folder(self):
        self.folder.rmdir()
        self.assertEqual(self.exit_code(), 2)


if __name__ == "__main__":
    unittest.main()
