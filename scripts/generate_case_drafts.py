"""가상 케이스 20건의 정답지 초안과 케이스 표를 만든다.

금액은 규칙으로 계산하고, 만든 뒤 검산식과 필요 서류 규칙으로 다시 검사한다.
실행: python3 scripts/generate_case_drafts.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "answers"
PLAN = ROOT / "docs" / "case-plan.md"

FORM_NAMES = {
    "6": "제6호", "7": "제7호", "8": "제8호", "9": "제9호", "10": "제10호",
    "11": "제11호", "12": "제12호", "12-2": "제12호의2", "13": "제13호",
    "itemized": "세부산정내역", "md-9": "처방전", "md-5-2": "진단서",
}


def receipt(form, name, provider, start, end=None, no=None, rows=(), cap=0, adj=None,
            prepaid=0, visit="외래", file_name=None):
    """rows: (행 이름, 본인부담금, 공단부담금, 전액본인부담, 비급여). adj: 끝수처리 뒤 ①②③④."""
    sums = [sum(r[i] for r in rows) for i in range(1, 5)]
    copay, insurer, full, non = adj or sums
    bill = copay + insurer + full + non
    doc = {
        "type": "receipt" if form in ("6", "7", "8", "9") else "simple_receipt",
        "form_no": form, "file_name": file_name, "patient_name": name, "provider_name": provider,
        "visit_type": visit, "visit_start": start, "visit_end": end or start, "receipt_no": no,
        "rows": [dict(zip(("name", "copay", "insurer", "full_copay", "noncovered"), r)) for r in rows],
        "copay_total": copay, "insurer_total": insurer, "full_copay_total": full,
        "noncovered_total": non, "bill_total": bill,
    }
    if form in ("6", "7", "8", "9"):
        patient = copay - cap + full + non
        due = patient - prepaid
        doc.update(cap_excess=cap, insurer_grand_total=insurer + cap, patient_total=patient,
                   prepaid=prepaid, due=due, paid_card=due, paid_cash_receipt=0, paid_cash=0,
                   paid_total=due, unpaid=0)
    else:
        patient = bill - insurer
        doc.update(patient_total=patient, due=patient, paid_card=patient, paid_cash_receipt=0,
                   paid_cash=0, paid_total=patient)
    return doc


def pharmacy(form, name, provider, date, no, copay, insurer, non=0, file_name=None):
    bill = copay + insurer + non
    patient = bill - insurer
    return {
        "type": "pharmacy_receipt", "form_no": form, "file_name": file_name, "patient_name": name,
        "provider_name": provider, "issue_date": date, "receipt_no": no,
        "rows": [{"name": "약품비", "copay": copay, "insurer": insurer, "full_copay": 0, "noncovered": non}],
        "copay_total": copay, "insurer_total": insurer, "full_copay_total": 0, "noncovered_total": non,
        "bill_total": bill, "patient_total": patient, "due": patient, "paid_card": patient,
        "paid_cash_receipt": 0, "paid_cash": 0, "paid_total": patient,
    }


def itemized(base, name=None, noncovered_diff=0, adjust=(0, 0, 0, 0), file_name=None):
    """base 영수증과 같은 진료의 세부내역서. adjust: 끝수처리 조정금액."""
    hap = [base["copay_total"], base["insurer_total"], base["full_copay_total"],
           base["noncovered_total"] - noncovered_diff]
    gye = [h - a for h, a in zip(hap, adjust)]
    lines, rows = [], base["rows"]
    remaining = list(gye)
    for i, r in enumerate(rows):
        vals = [r["copay"], r["insurer"], r["full_copay"], r["noncovered"]]
        if i == len(rows) - 1:
            vals = remaining
        else:
            remaining = [x - v for x, v in zip(remaining, vals)]
        lines.append({"item": r["name"], "date": base["visit_start"], "code": f"V{i + 1:03d}",
                      "name": f"가상 {r['name']}", "count": 1, "days": 1,
                      "total": sum(vals), "copay": vals[0], "insurer": vals[1],
                      "full_copay": vals[2], "noncovered": vals[3]})
    return {
        "type": "itemized_bill", "form_no": "itemized", "file_name": file_name,
        "patient_name": name or base["patient_name"], "provider_name": base["provider_name"],
        "visit_start": base["visit_start"], "visit_end": base["visit_end"], "lines": lines,
        "subtotal": {"copay": gye[0], "insurer": gye[1], "full_copay": gye[2], "noncovered": gye[3], "total": sum(gye)},
        "adjustment": {"copay": adjust[0], "insurer": adjust[1], "full_copay": adjust[2], "noncovered": adjust[3], "total": sum(adjust)},
        "grand_total": {"copay": hap[0], "insurer": hap[1], "full_copay": hap[2], "noncovered": hap[3], "total": sum(hap)},
    }


def rx(name, provider, date, code="J00", file_name=None):
    """의료법 시행규칙 별지 제9호서식. 환자가 요구하면 질병분류기호가 비어 있을 수 있다."""
    return {"type": "prescription", "form_no": "md-9", "file_name": file_name, "patient_name": name,
            "provider_name": provider, "insurance_type": "건강보험", "issue_date": date,
            "issue_no": f"{date.replace('-', '')}-001", "disease_code": code, "valid_days": 3,
            "drugs": [{"name": "가상의약품정", "code": "V900", "dose": 1, "daily": 3, "days": 3}],
            "visit_start": date, "visit_end": date}


def cert(kind, name, provider, start, end=None, file_name=None):
    doc = {"type": kind, "file_name": file_name, "patient_name": name, "provider_name": provider,
           "disease_name": "가상 진단명", "disease_code": "Z00", "visit_start": start, "visit_end": end or start}
    if kind == "diagnosis":
        # 의료법 시행규칙 별지 제5호의2서식
        doc.update(form_no="md-5-2", diagnosis_type="최종 진단", diagnosis_date=start,
                   admission_date=start, discharge_date=end or start, issue_date=end or start)
    return doc


def other(desc, form=None, file_name=None):
    return {"type": "other", "form_no": form, "description": desc, "file_name": file_name}


def payment_cert(name, provider, base):
    return {
        "type": "payment_cert", "form_no": "12-2", "patient_name": name, "provider_name": provider,
        "lines": [{"date": base["visit_start"], "visit_type": "외래",
                   "insurer": base["insurer_total"], "copay": base["copay_total"],
                   "full_copay": base["full_copay_total"], "noncovered": base["noncovered_total"],
                   "total": base["bill_total"], "patient_total": base["patient_total"],
                   "card": base["paid_card"], "cash_receipt": 0, "cash": 0}],
    }


# 자주 쓰는 행 이름
J, Y, GS, CH, TS, MUL = "진찰료", "투약 및 조제료 행위료", "검사료", "처치 및 수술료", "주사료 행위료", "재활 및 물리치료료"


def build_cases():
    c = []

    def add(category, purpose, claim_type, docs, conclusion="proceed", issues=(), capture="깨끗한 이미지",
            note=None, dept=None, cropped=False):
        c.append(dict(category=category, purpose=purpose, claim_type=claim_type, dept=dept, documents=docs,
                      conclusion=conclusion, issues=list(issues), capture=capture, note=note, cropped=cropped))

    # 단순 6건
    add("simple", "3만 원 이하 통원, 영수증만", "outpatient",
        [receipt("6", "김가온", "가상내과의원", "2026-10-02", no="2610-00101", rows=[(J, 4200, 9800, 0, 0)])], dept="내과")
    add("simple", "3만 원 이하 통원, 비급여 포함", "outpatient",
        [receipt("6", "이다온", "가상이비인후과의원", "2026-10-05", no="2610-00102",
                 rows=[(J, 4200, 9800, 0, 0), (GS, 0, 0, 0, 18000)])], dept="이비인후과")
    b = receipt("6", "박나래", "가상정형외과의원", "2026-10-07", no="2610-00103",
                rows=[(J, 4200, 9800, 0, 0), (MUL, 5800, 13500, 0, 40000)])
    add("simple", "3만 원 초과 통원, 처방전 있음", "outpatient", [b, rx("박나래", "가상정형외과의원", "2026-10-07", "M54")], dept="정형외과")
    b = receipt("6", "최하늘", "가상가정의학과의원", "2026-10-08", no="2610-00104",
                rows=[(J, 4200, 9800, 0, 0), (GS, 5800, 13500, 0, 70000)])
    add("simple", "3만~10만 원, 세부내역서와 금액 일치", "outpatient",
        [b, rx("최하늘", "가상가정의학과의원", "2026-10-08"), itemized(b)], dept="가정의학과")
    add("simple", "약국 약제비 영수증", "pharmacy",
        [pharmacy("10", "정보라", "가상약국", "2026-10-09", "2610-00105", 3000, 7000)])
    b = receipt("6", "한우주", "가상병원", "2026-10-10", "2026-10-12", "2610-00106", visit="입원",
                rows=[("입원료 4인실 이상", 40000, 160000, 0, 0), (GS, 20000, 80000, 0, 60000)])
    add("simple", "50만 원 이하 입원, 입퇴원확인서로 대체", "inpatient",
        [b, itemized(b), cert("visit_cert", "한우주", "가상병원", "2026-10-10", "2026-10-12")], dept="내과")

    # 양식·문맥 다양성 6건
    b = receipt("7", "윤세아", "가상내과의원", "2026-10-13", no="2610-00107",
                rows=[(J, 4200, 9800, 0, 0), ("초음파 진단료", 0, 0, 0, 50000), ("제증명수수료", 0, 0, 0, 3000)])
    add("variety", "괄호 칸 양식, 선택항목 포함", "outpatient", [b, rx("윤세아", "가상내과의원", "2026-10-13")], dept="내과")
    add("variety", "한방 표 양식", "outpatient",
        [receipt("8", "강도윤", "가상한의원", "2026-10-14", no="2610-00108",
                 rows=[(J, 3600, 8400, 0, 0), ("시술 및 처치료", 1500, 3500, 0, 0), ("한방물리요법료", 0, 0, 0, 10000)])], dept="한방")
    add("variety", "한방 괄호 칸 양식", "outpatient",
        [receipt("9", "오시우", "가상한방병원", "2026-10-15", no="2610-00109",
                 rows=[(J, 4800, 11200, 0, 0), ("한약(첩약)", 0, 0, 0, 20000)])], dept="한방")
    add("variety", "약제비 괄호 칸 양식", "pharmacy",
        [pharmacy("11", "서지안", "가상온누리약국", "2026-10-16", "2610-00110", 4500, 10500, 2000)])
    add("variety", "간이 외래 영수증 (수기)", "outpatient",
        [receipt("12", "임하준", "가상의원", "2026-10-17",
                 rows=[(J, 4200, 9800, 0, 0), (TS, 1200, 2800, 0, 0)])], capture="인쇄 후 스캔 느낌 효과", dept="내과",
        note="제12호에는 영수증 번호 칸이 없음")
    b = receipt("6", "신유나", "가상소아과의원", "2026-10-18", no="2610-00111", rows=[(J, 3000, 7000, 0, 5000)])
    add("variety", "납입 확인서 함께 제출. ①공단 ②본인 번호에 주의", "outpatient",
        [b, payment_cert("신유나", "가상소아과의원", b)], dept="소아과")

    # 문서 결합 6건
    b = receipt("6", "권태양", "가상내과의원", "2026-10-19", no="2610-00112",
                rows=[(J, 4200, 9800, 0, 0), (GS, 12800, 29900, 0, 30000)])
    add("combined", "영수증 + 세부내역서 + 처방전 모두 일치", "outpatient",
        [b, itemized(b), rx("권태양", "가상내과의원", "2026-10-19")], dept="내과")
    add("combined", "같은 날 병원 + 약국, 처방전 조제일 일치", "outpatient",
        [receipt("6", "조은별", "가상내과의원", "2026-10-20", no="2610-00113", rows=[(J, 4200, 9800, 0, 0), (GS, 3000, 7000, 0, 0)]),
         rx("조은별", "가상내과의원", "2026-10-20"),
         pharmacy("10", "조은별", "가상약국", "2026-10-20", "2610-00114", 2700, 6300)], dept="내과")
    add("combined", "여러 날 진료를 한 번에 청구, 합계로 금액 판단", "outpatient",
        [receipt("6", "장민재", "가상정형외과의원", "2026-10-21", no="2610-00115", rows=[(J, 4200, 9800, 0, 0), (MUL, 12000, 28000, 0, 0)]),
         receipt("6", "장민재", "가상정형외과의원", "2026-10-23", no="2610-00116", rows=[(J, 3000, 7000, 0, 0), (MUL, 12000, 28000, 0, 0)]),
         rx("장민재", "가상정형외과의원", "2026-10-21", "M54")], dept="정형외과",
        note="같은 환자·기관이지만 날짜와 번호가 달라 중복이 아님")
    b = receipt("6", "배서윤", "가상종합병원", "2026-09-01", "2026-09-05", "2609-00117", visit="입원",
                rows=[("입원료 4인실 이상", 80000, 320000, 0, 0), (CH, 150000, 600000, 0, 320000)])
    add("combined", "50만 원 초과 입원, 진단서 있음", "inpatient",
        [b, itemized(b), cert("diagnosis", "배서윤", "가상종합병원", "2026-09-01", "2026-09-05")], dept="외과")
    b = receipt("6", "홍지호", "가상정형외과의원", "2026-10-24", no="2610-00118",
                rows=[(J, 4200, 9800, 0, 0), (MUL, 8000, 18700, 0, 110000)])
    add("combined", "10만 원 초과 통원, 처방전 + 통원확인서", "outpatient",
        [b, rx("홍지호", "가상정형외과의원", "2026-10-24", "M54"), cert("visit_cert", "홍지호", "가상정형외과의원", "2026-10-24"), itemized(b)], dept="정형외과")
    b = receipt("6", "문채원", "가상내과의원", "2026-10-25", no="2610-00119",
                rows=[(J, 3124, 11916, 0, 0), (GS, 2012, 5877, 0, 30457)], adj=(5070, 17850, 0, 30450))
    add("combined", "세부내역서 끝수처리, 합계끼리는 일치", "outpatient",
        [b, rx("문채원", "가상내과의원", "2026-10-25"), itemized(b, adjust=(-66, 57, 0, -7))], dept="내과")

    # 저품질 5건: 값은 정상, 사진 상태만 나쁨
    b = receipt("7", "남기태", "가상내과의원", "2026-10-26", no="2610-00120",
                rows=[(J, 15000, 35000, 0, 0), (GS, 20000, 30000, 0, 0)])
    add("low_quality", "본인부담금 합계 칸만 흐림, 검산 C1로 확정 시험", "outpatient",
        [b, rx("남기태", "가상내과의원", "2026-10-26")], capture="본인부담금 합계 칸을 연하게 채움", dept="내과",
        note="두 경로가 다르게 읽고 C1로 고르면 정상. 사람도 못 읽으면 정답지를 다시 정한다")
    add("low_quality", "구겨진 사진", "outpatient",
        [receipt("6", "유하린", "가상의원", "2026-10-27", no="2610-00121", rows=[(J, 4200, 9800, 0, 0), (TS, 2000, 4700, 0, 0)])],
        capture="구긴 듯한 명암 효과", dept="내과")
    add("low_quality", "기울어진 사진", "outpatient",
        [receipt("7", "백시온", "가상의원", "2026-10-28", no="2610-00122", rows=[(J, 4200, 9800, 0, 3000)])],
        capture="15도 기울임 효과", dept="내과")
    add("low_quality", "그림자가 진 약국 영수증", "pharmacy",
        [pharmacy("10", "송예린", "가상약국", "2026-10-29", "2610-00123", 3300, 7700)], capture="금액 칸 그림자 효과")
    add("low_quality", "아래쪽 금액 칸이 잘린 사진", "outpatient",
        [receipt("6", "전우빈", "가상의원", "2026-10-30", no="2610-00124", rows=[(J, 4200, 9800, 0, 5000)])],
        conclusion="needs_review", issues=[{"cause": "NEEDS_REVIEW", "review_code": "CROPPED"}],
        capture="오른쪽 금액산정 칸이 안 나오게 잘라 저장", dept="내과", note="잘린 칸은 사람도 읽을 수 없어 정답 값이 null", cropped=True)

    # 예외·함정 7건
    b = receipt("6", "황도현", "가상정형외과의원", "2026-11-01", no="2611-00125",
                rows=[(J, 15000, 35000, 0, 0), (MUL, 20000, 30000, 0, 150000)])
    add("trap", "세부내역서 비급여가 42,000원 적음", "outpatient",
        [b, rx("황도현", "가상정형외과의원", "2026-11-01", "M54"), cert("visit_cert", "황도현", "가상정형외과의원", "2026-11-01"), itemized(b, noncovered_diff=42000)],
        "request_supplement", [{"cause": "DOC_MISMATCH", "rule": "X1", "amount_diff": 42000}, {"cause": "DOC_MISMATCH", "rule": "X2", "amount_diff": 42000}], dept="정형외과")
    b = receipt("6", "안소율", "가상내과의원", "2026-11-02", no="2611-00126", rows=[(J, 4200, 9800, 0, 0), (GS, 5800, 13500, 0, 25000)])
    add("trap", "세부내역서 환자 이름이 다름", "outpatient",
        [b, rx("안소율", "가상내과의원", "2026-11-02"), itemized(b, name="안소연")],
        "request_supplement", [{"cause": "DOC_MISMATCH", "rule": "X3"}], dept="내과")
    add("trap", "통원 5만 원대인데 처방전 없음", "outpatient",
        [receipt("6", "고은우", "가상내과의원", "2026-11-03", no="2611-00127", rows=[(J, 4200, 9800, 0, 0), (GS, 0, 0, 0, 50000)])],
        "request_supplement", [{"cause": "DOC_MISSING", "rule": "D2"}], dept="내과")
    b = receipt("6", "구하람", "가상의원", "2026-11-04", no="2611-00128", rows=[(J, 4200, 9800, 0, 0)])
    add("trap", "같은 영수증의 재발행본이 함께 들어옴", "outpatient",
        [b, dict(b, file_name="reissued")], "request_supplement", [{"cause": "DUPLICATE"}], dept="내과",
        note="재발행본은 발행일만 다르게 인쇄. 영수증 번호로 판단")
    add("trap", "카드 전표와 수납대장만 있고 영수증 없음", "outpatient",
        [other("카드 결제 전표"), other("본인부담금 수납대장", "13")],
        "request_supplement", [{"cause": "DOC_MISSING", "rule": "D1"}], capture="각각 촬영", dept="내과")
    b = receipt("6", "민서준", "가상병원", "2026-09-10", "2026-09-25", "2609-00129", visit="입원", cap=200000,
                rows=[("입원료 4인실 이상", 400000, 1600000, 0, 0), (CH, 200000, 800000, 0, 100000)])
    add("trap", "헷갈리지만 정상: 상한액 초과금이 있어 환자부담 총액이 작음", "inpatient",
        [b, itemized(b), cert("diagnosis", "민서준", "가상병원", "2026-09-10", "2026-09-25")], dept="내과",
        note="⑧ = (① − ⑤) + ③ + ④. 오탐하면 안 됨")
    b = receipt("6", "차유진", "가상정형외과의원", "2026-11-05", no="2611-00131",
                rows=[(J, 4200, 9800, 0, 0), (MUL, 10000, 23300, 0, 120000)])
    add("trap", "10만 원 초과인데 추가 증빙 없음", "outpatient",
        [b, rx("차유진", "가상정형외과의원", "2026-11-05", "M54"), itemized(b)],
        "needs_review", [{"cause": "NEEDS_REVIEW", "rule": "D3"}], dept="정형외과")
    return c


# 서류 이미지까지 만들어 실제로 쓰는 케이스. 나머지는 테스트에서만 쓴다.
USED_CASES = (1, 3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 19, 20, 23, 24, 25, 26, 27, 28, 29)
RECEIPTS = ("receipt", "simple_receipt", "pharmacy_receipt")
META_KEYS = ("type", "form_no", "file_name", "description")
# 사진에서 잘려 나간 칸. 서식 오른쪽 금액산정 칸과 머리글의 오른쪽 칸이다.
CROPPED_KEYS = ("visit_start", "visit_end", "receipt_no", "bill_total", "cap_excess", "insurer_grand_total", "patient_total", "prepaid", "due",
                "paid_card", "paid_cash_receipt", "paid_cash", "paid_total", "unpaid")


def flatten(doc, department=None, cropped=False):
    """서류 값을 schema/fields.json의 평면 키로 바꾼다."""
    fields = {}
    if doc["type"] in ("receipt", "simple_receipt") and department:
        fields["department"] = department
    for key, value in doc.items():
        if key in META_KEYS or (key in ("visit_start", "visit_end") and doc["type"] in ("prescription", "diagnosis")):
            continue
        if key == "rows":
            for row in value:
                fields.update({f"row:{row['name']}:{col}": v for col, v in row.items() if col != "name"})
        elif key in ("lines", "drugs"):
            prefix = "line" if key == "lines" else "drug"
            for i, line in enumerate(value):
                fields.update({f"{prefix}:{i}:{col}": v for col, v in line.items()})
        elif key in ("subtotal", "adjustment", "grand_total"):
            fields.update({f"{key}.{col}": v for col, v in value.items()})
        else:
            fields[key] = value
    if cropped:
        fields.update({key: None for key in CROPPED_KEYS if key in fields})
    return [{"file_name": doc["file_name"], "key": key, "value": value} for key, value in fields.items()]


def to_answer(cid, case):
    documents = []
    for d in case["documents"]:
        entry = {"file_name": d["file_name"], "type": d["type"], "form_no": d.get("form_no")}
        if d.get("description"):
            entry["description"] = d["description"]
        if case["cropped"]:
            entry["flags"] = ["CROPPED"]
        documents.append(entry)
    return {"case_id": cid, "category": case["category"], "source_type": "synthetic", "draft": True,
            "purpose": case["purpose"], "claim_type": case["claim_type"], "capture": case["capture"],
            "note": case["note"], "conclusion": case["conclusion"], "documents": documents,
            "fields": [f for d in case["documents"] for f in flatten(d, case["dept"], case["cropped"])],
            "issues": case["issues"]}


def check_amounts(d):
    errors = []
    if d["type"] == "receipt":
        checks = {
            "C1": d["bill_total"] == d["copay_total"] + d["insurer_total"] + d["full_copay_total"] + d["noncovered_total"],
            "C2": d["insurer_grand_total"] == d["insurer_total"] + d["cap_excess"],
            "C3": d["patient_total"] == d["copay_total"] - d["cap_excess"] + d["full_copay_total"] + d["noncovered_total"],
            "C4": d["due"] == d["patient_total"] - d["prepaid"],
            "C5": d["paid_total"] == d["paid_card"] + d["paid_cash_receipt"] + d["paid_cash"],
            "C6": d["unpaid"] == d["due"] - d["paid_total"],
        }
    elif d["type"] in ("simple_receipt", "pharmacy_receipt"):
        checks = {
            "P1": d["bill_total"] == d["copay_total"] + d["insurer_total"] + d["full_copay_total"] + d["noncovered_total"],
            "P2": d["patient_total"] == d["bill_total"] - d["insurer_total"],
            "P3": d["paid_total"] == d["paid_card"] + d["paid_cash_receipt"] + d["paid_cash"],
        }
    elif d["type"] == "payment_cert":
        checks = {}
        for line in d["lines"]:
            checks["N1"] = line["total"] == line["insurer"] + line["copay"] + line["full_copay"] + line["noncovered"]
            checks["N2"] = line["patient_total"] == line["copay"] + line["full_copay"] + line["noncovered"]
    elif d["type"] == "itemized_bill":
        checks = {}
        for key in ("copay", "insurer", "full_copay", "noncovered", "total"):
            checks["S2_" + key] = sum(l[key] for l in d["lines"]) == d["subtotal"][key]
            checks["S3_" + key] = d["subtotal"][key] + d["adjustment"][key] == d["grand_total"][key]
    else:
        checks = {}
    errors += [k for k, ok in checks.items() if not ok]
    if d["type"] in RECEIPTS and d.get("rows"):
        for key, total in (("copay", "copay_total"), ("insurer", "insurer_total"), ("noncovered", "noncovered_total")):
            if abs(sum(r[key] for r in d["rows"]) - d[total]) > 100:
                errors.append("S1_" + key)
    return errors


def derive_issues(case):
    """정답지의 이슈가 규칙과 맞는지 다시 계산한다."""
    docs, found = case["documents"], set()
    receipts = [d for d in docs if d["type"] in RECEIPTS]
    if not receipts:
        found.add("D1")
    total = sum(d["patient_total"] for d in receipts)
    has = lambda *kinds: any(d["type"] in kinds for d in docs)
    numbers = [d["receipt_no"] for d in receipts if d.get("receipt_no")]
    duplicate = len(numbers) != len(set(numbers))
    if duplicate:
        total = sum(d["patient_total"] for d in {d["receipt_no"]: d for d in receipts}.values())
    if case["claim_type"] == "outpatient" and receipts:
        if total > 30000 and not any(d["type"] == "prescription" and d.get("disease_code") for d in docs):
            found.add("D2")
        if total > 100000 and not has("diagnosis", "visit_cert"):
            found.add("D3")
    if duplicate:
        found.add("DUPLICATE")
    for d in docs:
        if d["type"] == "itemized_bill":
            base = next(r for r in receipts if r["visit_start"] == d["visit_start"])
            pairs = (("copay", "copay_total"), ("insurer", "insurer_total"), ("full_copay", "full_copay_total"), ("noncovered", "noncovered_total"))
            if any(d["grand_total"][a] != base[b] for a, b in pairs):
                found.add("X1")
            if d["grand_total"]["total"] != base["bill_total"]:
                found.add("X2")
    names = {d["patient_name"] for d in docs if d.get("patient_name")}
    if len(names) > 1:
        found.add("X3")
    return found


def build_answers():
    """번호별 정답지와 검사 문제. 쓰지 않는 케이스도 함께 만든다."""
    cases = build_cases()
    assert len(cases) == 30
    answers, problems = {}, []
    for i, case in enumerate(cases, 1):
        cid = f"case_{i:02d}"
        for j, d in enumerate(case["documents"], 1):
            if not d.get("file_name") or d["file_name"] == "reissued":
                d["file_name"] = f"{cid}_doc{j}_{d['type']}"
            errors = check_amounts(d)
            if errors:
                problems.append(f"{cid} {d['file_name']}: {errors}")
        expected = {x.get("rule") or x["cause"] for x in case["issues"] if x.get("rule") or x["cause"] == "DUPLICATE"}
        found = derive_issues(case)
        if expected != found:
            problems.append(f"{cid}: 정답 {expected} / 규칙 {found}")
        answers[i] = to_answer(cid, case)
    return cases, answers, problems


def main():
    cases, answers, problems = build_answers()
    if problems:
        raise SystemExit("검사 실패\n" + "\n".join(problems))
    rows, counts = [], {}
    ANSWERS.mkdir(exist_ok=True)
    for i in USED_CASES:
        case, answer = cases[i - 1], answers[i]
        (ANSWERS / f"{answer['case_id']}.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        forms = ", ".join(dict.fromkeys(FORM_NAMES.get(d.get("form_no"), {"prescription": "처방전", "diagnosis": "진단서", "visit_cert": "확인서", "other": "기타"}.get(d["type"], d["type"])) for d in case["documents"]))
        receipts = [d for d in case["documents"] if d["type"] in RECEIPTS]
        amount = sum({d.get("receipt_no") or id(d): d["patient_total"] for d in receipts}.values())
        issue = ", ".join(x.get("rule") or x.get("review_code") or x["cause"] for x in case["issues"]) or "없음"
        rows.append(f"| {i:02d} | {case['category']} | {case['purpose']} | {forms} | {amount:,} | {case['capture']} | {issue} | {case['conclusion']} |")
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    PLAN.write_text(
        "# 가상 케이스 20건 초안\n\n"
        "`scripts/generate_case_drafts.py`로 만들었다. 금액 검산식과 필요 서류 규칙을 통과한 값이다. "
        "케이스별 값은 `answers/case_NN.json`에, 서류 이미지는 `cases/case_NN/`에 있고, 형식은 `schema/answer.schema.json`을 따른다. "
        "번호는 처음 정한 30건의 번호를 유지해 중간이 비어 있다.\n\n"
        "| 번호 | 유형 | 목적 | 서식 | 환자부담 합계 | 제작 상태 | 이슈 | 결론 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print("통과", len(USED_CASES), counts)


if __name__ == "__main__":
    main()
