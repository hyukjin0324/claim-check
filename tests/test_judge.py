"""판정 규칙 테스트. 실행: python3 -m unittest discover tests"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from judge import judge_claim  # noqa: E402
from judge.perfect import answer_to_extract  # noqa: E402
from generate_case_drafts import build_answers  # noqa: E402
from score_rules import load_answers, score_case  # noqa: E402

try:
    import jsonschema
except ImportError:
    jsonschema = None


# 규칙 시험에는 쓰지 않는 케이스도 필요해서 파일 대신 생성 스크립트에서 읽는다.
ALL_ANSWERS = build_answers()[1]


def load_case(number):
    return answer_to_extract(copy.deepcopy(ALL_ANSWERS[number]))


def load_fake(name):
    return json.loads((ROOT / "fixtures" / f"{name}.extract.json").read_text(encoding="utf-8"))


def read_as(extract, doc_id, key, a, b, confidence=None):
    doc = next(d for d in extract["documents"] if d["doc_id"] == doc_id)
    field = next((f for f in doc["fields"] if f["key"] == key), None)
    if field is None:
        field = {"key": key, "path_a": {"value": None}, "path_b": {"value": None}}
        doc["fields"].append(field)
    field["path_a"]["value"], field["path_b"]["value"] = a, b
    if confidence is not None:
        field["path_a"]["ocr_confidence"] = confidence
    return extract


def drop_doc(extract, doc_type):
    extract["documents"] = [d for d in extract["documents"] if d["type"] != doc_type]
    return extract


def field(result, doc_id, key):
    return next(f for f in result["fields"] if f["doc_id"] == doc_id and f["key"] == key)


def codes(result):
    return {(i["cause"], i["rule"], i["review_code"]) for i in result["issues"]}


class ConfirmTest(unittest.TestCase):
    def test_agree_with_passing_equation(self):
        result = judge_claim(load_fake("fake_agree"))
        copay = field(result, "d1", "copay_total")
        self.assertEqual((copay["status"], copay["value"], copay["basis"]["type"]), ("confirmed", 4200, "agree"))
        self.assertIn("C1", copay["basis"]["rules"])
        self.assertEqual(result["conclusion"], "proceed")

    def test_checksum_picks_the_passing_path(self):
        result = judge_claim(load_fake("fake_checksum"))
        copay = field(result, "d1", "copay_total")
        self.assertEqual((copay["status"], copay["value"], copay["basis"]["type"]), ("confirmed", 4200, "checksum"))
        self.assertEqual(result["conclusion"], "proceed")

    def test_checksum_picks_path_b_too(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "copay_total", 4800, 4200))
        self.assertEqual(field(result, "d1", "copay_total")["value"], 4200)

    def test_unstable_base_blocks_choice(self):
        result = judge_claim(load_fake("fake_unstable"))
        insurer = field(result, "d1", "insurer_total")
        self.assertEqual((insurer["status"], insurer["value"], insurer["review_code"]), ("needs_review", None, "UNSTABLE_BASE"))
        self.assertEqual(insurer["candidates"], {"path_a": 9800, "path_b": 9300})
        self.assertEqual(field(result, "d1", "bill_total")["review_code"], "UNSTABLE_BASE")
        self.assertEqual(result["conclusion"], "needs_review")
        self.assertIn("READ_ERROR", {i["cause"] for i in result["issues"]})

    def test_confirmed_value_becomes_base_for_next_equation(self):
        # 본인부담금을 C3로 먼저 정하면 그 값으로 C1에서 총액도 고를 수 있다.
        extract = read_as(load_fake("fake_agree"), "d1", "copay_total", 4200, 4800)
        result = judge_claim(read_as(extract, "d1", "bill_total", 67000, 67600))
        self.assertEqual(field(result, "d1", "copay_total")["basis"], {"type": "checksum", "rules": ["C3"]})
        self.assertEqual(field(result, "d1", "bill_total")["value"], 67000)

    def test_both_paths_fail_equation(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "copay_total", 4100, 4800))
        self.assertEqual(field(result, "d1", "copay_total")["review_code"], "READ_CONFLICT")
        self.assertEqual(result["conclusion"], "needs_review")

    def test_agree_but_equation_broken(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "bill_total", 68000, 68000))
        self.assertEqual(field(result, "d1", "bill_total")["review_code"], "INTERNAL_MISMATCH")
        issue = next(i for i in result["issues"] if i["rule"] == "C1")
        self.assertEqual((issue["cause"], issue["amount_diff"]), ("NEEDS_REVIEW", 1000))

    def test_one_side_must_pass_equation(self):
        passed = judge_claim(read_as(load_fake("fake_agree"), "d1", "copay_total", 4200, None))
        self.assertEqual(field(passed, "d1", "copay_total")["status"], "confirmed")
        failed = judge_claim(read_as(load_fake("fake_agree"), "d1", "copay_total", 4100, None))
        self.assertEqual(field(failed, "d1", "copay_total")["status"], "needs_review")

    def test_text_without_equation_needs_agreement(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "provider_name", "가상내과의원", "가상내과병원"))
        self.assertEqual(field(result, "d1", "provider_name")["review_code"], "READ_CONFLICT")

    def test_row_values_are_not_checksummed(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "row:진찰료:copay", 4200, 4300))
        self.assertEqual(field(result, "d1", "row:진찰료:copay")["review_code"], "READ_CONFLICT")

    def test_required_field_missing(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "patient_name", None, None))
        self.assertEqual(field(result, "d1", "patient_name")["review_code"], "MISSING_FIELD")

    def test_masked_name_keeps_masked_value(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "patient_name", "윤세아", "윤*아"))
        self.assertEqual(field(result, "d1", "patient_name")["value"], "윤*아")

    def test_low_ocr_is_not_confirmed_even_if_equation_passes(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "copay_total", 4200, 4200, confidence=0.3))
        self.assertEqual(field(result, "d1", "copay_total")["review_code"], "LOW_OCR")
        self.assertEqual(result["conclusion"], "needs_review")

    def test_low_ocr_side_can_lose_to_equation(self):
        result = judge_claim(read_as(load_fake("fake_agree"), "d1", "copay_total", 4800, 4200, confidence=0.3))
        self.assertEqual(field(result, "d1", "copay_total")["value"], 4200)

    def test_cap_excess_is_not_an_error(self):
        self.assertEqual(judge_claim(load_case(29))["conclusion"], "proceed")

    def test_rounded_rows_within_tolerance(self):
        self.assertEqual(judge_claim(load_case(18))["conclusion"], "proceed")

    def test_rows_beyond_tolerance_need_review(self):
        result = judge_claim(read_as(load_case(1), "d1", "row:진찰료:copay", 5000, 5000))
        self.assertIn(("NEEDS_REVIEW", "S1", "INTERNAL_MISMATCH"), codes(result))


class RoundingTest(unittest.TestCase):
    def paid(self, amount):
        """본인부담금 4,217원인 영수증에 납부할 금액을 넣는다."""
        extract = load_case(1)
        read_as(extract, "d1", "copay_total", 4217, 4217)
        read_as(extract, "d1", "bill_total", 14017, 14017)
        read_as(extract, "d1", "patient_total", 4217, 4217)
        for key in ("due", "paid_total", "paid_card"):
            read_as(extract, "d1", key, amount, amount)
        return extract

    def test_combined_covered_rows_use_tolerance(self):
        extract = load_case(1)
        doc = extract["documents"][0]
        doc["fields"] = [f for f in doc["fields"] if not f["key"].startswith("row:")]
        self.assertEqual(judge_claim(read_as(copy.deepcopy(extract), "d1", "row:진찰료:covered", 14004, 14004))["conclusion"], "proceed")
        found = codes(judge_claim(read_as(extract, "d1", "row:진찰료:covered", 15000, 15000)))
        self.assertIn(("NEEDS_REVIEW", "S1", "INTERNAL_MISMATCH"), found)

    def test_due_with_dropped_ones_passes(self):
        for amount in (4217, 4210, 4200):
            with self.subTest(amount=amount):
                result = judge_claim(self.paid(amount))
                self.assertEqual(field(result, "d1", "due")["value"], amount)
                self.assertEqual(result["conclusion"], "proceed")

    def test_due_not_rounded_is_mismatch(self):
        for amount in (4201, 4215, 4190, 4220):
            with self.subTest(amount=amount):
                self.assertIn(("NEEDS_REVIEW", "C4", "INTERNAL_MISMATCH"), codes(judge_claim(self.paid(amount))))

    def test_two_values_inside_range_are_ambiguous(self):
        extract = self.paid(4217)
        read_as(extract, "d1", "due", 4210, 4200)
        for key in ("paid_total", "paid_card", "unpaid"):
            read_as(extract, "d1", key, None, None)
        self.assertEqual(field(judge_claim(extract), "d1", "due")["review_code"], "AMBIGUOUS_VALUE")


def set_visit(extract, doc_id, date, total, insurer, patient):
    for column, value in (("total", total), ("insurer", insurer), ("patient_total", patient)):
        read_as(extract, doc_id, f"visit:{date}:{column}", value, value)
    return extract


class VisitBillTest(unittest.TestCase):
    """여러 날을 묶은 내역서. case 4의 세부내역서를 이틀짜리 내역서로 바꾼다."""

    def build(self, second=None):
        extract = load_case(4)
        doc = extract["documents"][2]
        doc["fields"] = [f for f in doc["fields"] if f["key"] in ("patient_name", "provider_name", "visit_start", "visit_end", "grand_total.total")]
        receipt = {f["key"]: f["path_a"]["value"] for f in extract["documents"][0]["fields"]}
        date = receipt["visit_start"]
        set_visit(extract, "d3", date, receipt["bill_total"], receipt["insurer_total"], receipt["patient_total"])
        total = receipt["bill_total"]
        if second:
            set_visit(extract, "d3", second, 1000, 300, 700)
            total += 1000
        read_as(extract, "d3", "grand_total.total", total, total)
        return extract

    def test_visit_matches_receipt(self):
        self.assertEqual(judge_claim(self.build())["conclusion"], "proceed")

    def test_missing_receipt_for_a_visit_needs_review(self):
        result = judge_claim(self.build("2026-10-09"))
        self.assertIn(("NEEDS_REVIEW", "X7", "UNVERIFIED_INPUT"), codes(result))
        self.assertNotIn("DOC_MISMATCH", {i["cause"] for i in result["issues"]})

    def test_visit_amount_differs(self):
        extract = self.build()
        date = next(f["path_a"]["value"] for f in extract["documents"][0]["fields"] if f["key"] == "visit_start")
        read_as(extract, "d3", f"visit:{date}:total", 1, 1)
        self.assertIn(("DOC_MISMATCH", "X7", None), codes(judge_claim(extract)))

    def test_visit_sum_must_match_grand_total(self):
        extract = read_as(self.build(), "d3", "grand_total.total", 1, 1)
        self.assertIn(("NEEDS_REVIEW", "S4", "INTERNAL_MISMATCH"), codes(judge_claim(extract)))


class CrossCheckTest(unittest.TestCase):
    def test_mismatch_amount(self):
        result = judge_claim(load_case(24))
        self.assertEqual({i["rule"]: i["amount_diff"] for i in result["issues"]}, {"X1": 42000, "X2": 42000})
        self.assertEqual(result["conclusion"], "request_supplement")

    def test_read_error_does_not_become_doc_mismatch(self):
        extract = load_case(4)
        read_as(extract, "d3", "grand_total.noncovered", 70000, 28000)
        result = judge_claim(extract)
        self.assertNotIn("DOC_MISMATCH", {i["cause"] for i in result["issues"]})
        self.assertIn(("NEEDS_REVIEW", "X1", "UNVERIFIED_INPUT"), codes(result))
        self.assertEqual(result["conclusion"], "needs_review")

    def test_name_mismatch_and_masked_name(self):
        self.assertIn(("DOC_MISMATCH", "X3", None), codes(judge_claim(load_case(25))))
        extract = read_as(load_case(3), "d1", "patient_name", "박*래", "박*래")
        self.assertEqual(judge_claim(extract)["conclusion"], "proceed")

    def test_date_outside_receipt_period(self):
        extract = read_as(load_case(4), "d3", "visit_start", "2026-10-09", "2026-10-09")
        self.assertIn(("DOC_MISMATCH", "X4", None), codes(judge_claim(extract)))

    def test_provider_mismatch(self):
        extract = read_as(load_case(3), "d2", "provider_name", "다른의원", "다른의원")
        self.assertIn(("DOC_MISMATCH", "X5", None), codes(judge_claim(extract)))

    def test_pharmacy_date_outside_prescription_period(self):
        extract = read_as(load_case(14), "d3", "issue_date", "2026-10-24", "2026-10-24")
        self.assertIn(("DOC_MISMATCH", "X6", None), codes(judge_claim(extract)))


class RequiredDocsTest(unittest.TestCase):
    def test_prescription_needed_over_30000(self):
        self.assertIn(("DOC_MISSING", "D2", None), codes(judge_claim(load_case(26))))

    def test_blank_disease_code_is_missing(self):
        extract = read_as(load_case(3), "d2", "disease_code", None, None)
        self.assertIn(("DOC_MISSING", "D2", None), codes(judge_claim(extract)))

    def test_unconfirmed_disease_code_is_not_missing(self):
        extract = read_as(load_case(3), "d2", "disease_code", "M54", "M64")
        found = codes(judge_claim(extract))
        self.assertIn(("NEEDS_REVIEW", "D2", "UNVERIFIED_INPUT"), found)
        self.assertNotIn(("DOC_MISSING", "D2", None), found)

    def test_unconfirmed_amount_is_not_missing(self):
        extract = read_as(load_case(26), "d1", "patient_total", 54300, 59200)
        found = codes(judge_claim(extract))
        self.assertIn(("NEEDS_REVIEW", "D2", "UNVERIFIED_INPUT"), found)
        self.assertNotIn(("DOC_MISSING", "D2", None), found)

    def test_receipt_missing(self):
        self.assertEqual(codes(judge_claim(load_case(28))), {("DOC_MISSING", "D1", None)})

    def test_extra_evidence_over_100000(self):
        result = judge_claim(load_case(30))
        self.assertEqual(codes(result), {("NEEDS_REVIEW", "D3", None)})
        self.assertEqual(result["conclusion"], "needs_review")

    def test_over_100000_with_no_documents_is_review_first(self):
        extract = load_case(30)
        extract["documents"] = extract["documents"][:1]
        result = judge_claim(extract)
        self.assertEqual(codes(result), {("DOC_MISSING", "D2", None), ("NEEDS_REVIEW", "D3", None)})
        self.assertEqual(result["conclusion"], "needs_review")

    def test_special_department_skips_simplified_rule(self):
        extract = read_as(load_case(1), "d1", "department", "피부과", "피부과")
        self.assertEqual(codes(judge_claim(extract)), {("NEEDS_REVIEW", "D4", None)})

    def test_inpatient_missing_itemized(self):
        result = judge_claim(drop_doc(load_case(16), "itemized_bill"))
        self.assertIn(("DOC_MISSING", "D5", None), codes(result))

    def test_inpatient_small_can_use_certificate(self):
        self.assertEqual(judge_claim(load_case(6))["conclusion"], "proceed")

    def test_inpatient_large_cannot_use_certificate(self):
        extract = load_case(16)
        next(d for d in extract["documents"] if d["type"] == "diagnosis")["type"] = "visit_cert"
        self.assertIn(("DOC_MISSING", "D5", None), codes(judge_claim(extract)))

    def test_duplicate_counted_once(self):
        extract = load_case(27)
        result = judge_claim(extract)
        self.assertEqual(codes(result), {("DUPLICATE", None, None)})

    def test_same_patient_on_other_days_is_not_duplicate(self):
        self.assertEqual(judge_claim(load_case(15))["issues"], [])

    def test_previous_claim_duplicate(self):
        result = judge_claim(load_case(1), previous_receipts={"2610-00101"})
        self.assertEqual(codes(result), {("DUPLICATE", None, None)})


class RuleReviewTest(unittest.TestCase):
    """외부 검토에서 찾은 잘못 통과와 잘못 경고."""

    def test_inpatient_needs_medical_receipt(self):
        extract = load_case(29)
        pharmacy = load_case(5)["documents"][0]
        pharmacy["doc_id"] = "d9"
        extract["documents"] = [pharmacy] + [d for d in extract["documents"] if d["type"] != "receipt"]
        self.assertIn(("DOC_MISSING", "D5", None), codes(judge_claim(extract)))

    def drop_disease_name(self, extract, kind):
        doc = next(d for d in extract["documents"] if d["type"] == kind)
        doc["fields"] = [f for f in doc["fields"] if f["key"] not in ("disease_name", "disease_code")]
        return extract

    def test_diagnosis_without_name_is_missing(self):
        result = judge_claim(self.drop_disease_name(load_case(29), "diagnosis"))
        self.assertIn(("DOC_MISSING", "D5", None), codes(result))

    def test_unconfirmed_diagnosis_name_is_not_missing(self):
        found = codes(judge_claim(read_as(load_case(29), "d3", "disease_name", "가상 진단명", "가상 병명")))
        self.assertIn(("NEEDS_REVIEW", "D5", "UNVERIFIED_INPUT"), found)
        self.assertNotIn(("DOC_MISSING", "D5", None), found)

    def test_certificate_without_name_is_not_evidence(self):
        result = judge_claim(self.drop_disease_name(load_case(17), "visit_cert"))
        self.assertIn(("NEEDS_REVIEW", "D3", None), codes(result))

    def test_evidence_can_replace_prescription(self):
        extract = read_as(load_case(17), "d2", "disease_code", None, None)
        self.assertNotIn(("DOC_MISSING", "D2", None), codes(judge_claim(extract)))

    def test_new_department_name_is_special(self):
        extract = read_as(load_case(1), "d1", "department", "비뇨의학과", "비뇨의학과")
        self.assertEqual(codes(judge_claim(extract)), {("NEEDS_REVIEW", "D4", None)})

    def two_pairs(self):
        extract = load_case(14)
        prescription = copy.deepcopy(next(d for d in extract["documents"] if d["type"] == "prescription"))
        pharmacy = copy.deepcopy(next(d for d in extract["documents"] if d["type"] == "pharmacy_receipt"))
        prescription["doc_id"], pharmacy["doc_id"] = "d8", "d9"
        extract["documents"] += [prescription, pharmacy]
        read_as(extract, "d8", "issue_date", "2026-10-28", "2026-10-28")
        read_as(extract, "d9", "issue_date", "2026-10-28", "2026-10-28")
        read_as(extract, "d9", "receipt_no", "2610-09999", "2610-09999")
        return extract

    def test_two_prescription_pairs_are_not_crossed(self):
        self.assertNotIn(("DOC_MISMATCH", "X6", None), codes(judge_claim(self.two_pairs())))

    def test_pharmacy_outside_every_prescription(self):
        extract = read_as(self.two_pairs(), "d9", "issue_date", "2026-11-20", "2026-11-20")
        self.assertIn(("DOC_MISMATCH", "X6", None), codes(judge_claim(extract)))

    def test_prescription_period_counts_issue_day(self):
        extract = read_as(load_case(14), "d2", "valid_days", 1, 1)
        self.assertNotIn(("DOC_MISMATCH", "X6", None), codes(judge_claim(extract)))
        read_as(extract, "d3", "issue_date", "2026-10-21", "2026-10-21")
        self.assertIn(("DOC_MISMATCH", "X6", None), codes(judge_claim(extract)))

    def test_masked_name_does_not_join_different_names(self):
        extract = load_case(4)
        for doc_id, name in (("d1", "김*수"), ("d2", "김철수"), ("d3", "김민수")):
            read_as(extract, doc_id, "patient_name", name, name)
        self.assertIn(("DOC_MISMATCH", "X3", None), codes(judge_claim(extract)))

    def test_same_number_at_other_provider_is_not_duplicate(self):
        extract = load_case(27)
        read_as(extract, "d2", "provider_name", "다른의원", "다른의원")
        self.assertNotIn(("DUPLICATE", None, None), codes(judge_claim(extract)))

    def test_unconfirmed_provider_is_not_called_duplicate(self):
        extract = read_as(load_case(27), "d2", "provider_name", "가상의원", "가상의원2")
        found = codes(judge_claim(extract))
        self.assertNotIn(("DUPLICATE", None, None), found)
        self.assertIn(("NEEDS_REVIEW", "F9", "UNVERIFIED_INPUT"), found)


class ConclusionTest(unittest.TestCase):
    def test_review_wins_over_supplement(self):
        extract = read_as(load_case(26), "d1", "provider_name", "가상내과의원", "가상내과병원")
        result = judge_claim(extract)
        self.assertEqual(result["conclusion"], "needs_review")
        self.assertIn(("DOC_MISSING", "D2", None), codes(result))

    def test_cropped_is_one_issue(self):
        self.assertEqual(codes(judge_claim(load_case(23))), {("NEEDS_REVIEW", None, "CROPPED")})

    def test_unknown_doc(self):
        extract = load_case(1)
        extract["documents"][0]["type_confidence"] = 0.4
        self.assertIn(("NEEDS_REVIEW", None, "UNKNOWN_DOC"), codes(judge_claim(extract)))

    def test_same_input_same_output(self):
        extract = load_case(24)
        self.assertEqual(judge_claim(copy.deepcopy(extract)), judge_claim(copy.deepcopy(extract)))

    def test_issues_sorted_by_amount(self):
        extract = read_as(load_case(24), "d1", "bill_total", 251000, 251000)
        amounts = [i["amount_diff"] or 0 for i in judge_claim(extract)["issues"]]
        self.assertEqual(amounts, sorted(amounts, reverse=True))


class RuleScoreTest(unittest.TestCase):
    def test_all_cases_match_answers(self):
        for answer in load_answers():
            score = score_case(answer)
            with self.subTest(answer["case_id"]):
                self.assertTrue(score["conclusion_ok"])
                self.assertEqual(score["expected"], score["found"])
                self.assertEqual(score["wrong_values"], [])
                self.assertEqual(score["wrong_amounts"], [])


class MisreadSweepTest(unittest.TestCase):
    """모든 케이스의 모든 칸을 하나씩 잘못 읽혀 본다."""

    def sweep(self, misread):
        for answer in load_answers():
            base = judge_claim(answer_to_extract(answer))
            base_support = {(i["cause"], i["rule"]) for i in base["issues"] if i["cause"] in ("DOC_MISMATCH", "DOC_MISSING", "DUPLICATE")}
            truth = answer_to_extract(answer)
            for doc_index, doc in enumerate(truth["documents"]):
                for field_index, item in enumerate(doc["fields"]):
                    if item["path_a"]["value"] is None:
                        continue
                    extract = copy.deepcopy(truth)
                    target = extract["documents"][doc_index]["fields"][field_index]
                    misread(target)
                    yield answer["case_id"], item, judge_claim(extract), base_support

    @staticmethod
    def wrong_value(value):
        return value + 1000 if isinstance(value, int) else f"{value}오"

    def test_one_path_misread_never_confirms_wrong_value(self):
        def misread(target):
            target["path_b"]["value"] = self.wrong_value(target["path_b"]["value"])

        for case_id, item, result, support in self.sweep(misread):
            with self.subTest(case=case_id, key=item["key"]):
                wrong = self.wrong_value(item["path_a"]["value"])
                confirmed = [f["value"] for f in result["fields"] if f["key"] == item["key"] and f["status"] == "confirmed"]
                self.assertNotIn(wrong, confirmed)
                new = {(i["cause"], i["rule"]) for i in result["issues"] if i["cause"] in ("DOC_MISMATCH", "DOC_MISSING", "DUPLICATE")} - support
                self.assertEqual(new, set())

    def test_one_path_blank_never_invents_a_finding(self):
        def misread(target):
            target["path_b"]["value"] = None

        for case_id, item, result, support in self.sweep(misread):
            with self.subTest(case=case_id, key=item["key"]):
                new = {(i["cause"], i["rule"]) for i in result["issues"] if i["cause"] in ("DOC_MISMATCH", "DOC_MISSING", "DUPLICATE")} - support
                self.assertEqual(new, set())

    def test_both_paths_same_wrong_total_is_caught(self):
        def misread(target):
            target["path_a"]["value"] = target["path_b"]["value"] = self.wrong_value(target["path_a"]["value"])

        totals = {"copay_total", "insurer_total", "bill_total", "patient_total", "paid_total"}
        for case_id, item, result, _ in self.sweep(misread):
            if item["key"] in totals:
                with self.subTest(case=case_id, key=item["key"]):
                    self.assertEqual(result["conclusion"], "needs_review")


@unittest.skipIf(jsonschema is None, "jsonschema가 없어 건너뜀")
class SchemaTest(unittest.TestCase):
    def schema(self, name):
        return json.loads((ROOT / "schema" / name).read_text(encoding="utf-8"))

    def test_answers(self):
        for answer in load_answers():
            jsonschema.validate(answer, self.schema("answer.schema.json"))

    def test_extract_and_judge(self):
        for name in ("fake_agree", "fake_checksum", "fake_unstable"):
            extract = load_fake(name)
            jsonschema.validate(extract, self.schema("extract_output.schema.json"))
            jsonschema.validate(judge_claim(extract), self.schema("judge_output.schema.json"))
        for answer in load_answers():
            extract = answer_to_extract(answer)
            jsonschema.validate(extract, self.schema("extract_output.schema.json"))
            jsonschema.validate(judge_claim(extract), self.schema("judge_output.schema.json"))


if __name__ == "__main__":
    unittest.main()
