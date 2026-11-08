"""최종 제출 데이터셋을 만든다. 데이터셋 PDF, 정답지, 유형표.

필요: pip install pymupdf openpyxl
실행: python3 scripts/export_final.py

cases/의 가상 케이스 이미지는 PDF로 묶고, submission/mission2/시험용/의 PDF는 그대로 복사한다.
기대값은 아래 SETS에만 적는다. 설정 #13 실행 결과와 비교할 때도 이 값을 쓴다.
"""
import json
import shutil
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "submission" / "final"
TEST_DIR = ROOT / "submission" / "mission2" / "시험용"
TYPES_TEMPLATE = ROOT / "submission" / "mission2" / "컴학감동_미션2_유형표.xlsx"
TEAM = "컴학감동"
OUTPUT_KEYS = ["patient_name", "provider_name", "decision", "cause", "reason", "missing_documents", "mismatches"]
DECISIONS = ["심사 진행", "보완 요청", "검토 필요"]
DOC_NAMES = {"receipt": "진료비 영수증", "pharmacy_receipt": "약제비 영수증", "simple_receipt": "진료비 영수증(간이)",
             "prescription": "처방전", "visit_cert": "통원확인서", "itemized_bill": "세부내역서", "diagnosis": "진단서",
             "payment_cert": "납입확인서", "other": "기타 문서"}
OK = ("심사 진행", "없음", [], [])

# (원본, 유형, 확인하려는 점, (decision, cause, missing_documents, mismatches), reason)
# 원본이 숫자면 cases/case_NN, 문자열이면 시험용 PDF 이름(이때 이름·기관·서류는 직접 적는다)
SETS = [
    (1, "① 단순", "3만 원 이하 통원, 영수증만", OK, "환자부담 총액 4,200원의 3만 원 이하 통원이라 영수증만으로 충분하고 검산이 맞음"),
    (3, "① 단순 · ③ 결합", "처방전이 있는 3만 원 초과 통원", OK, "환자부담 총액이 3만 원을 넘고 질병분류기호가 있는 처방전이 있음"),
    (5, "① 단순 · ② 다양성", "약국 약제비 영수증만", OK, "약제비 영수증 검산이 맞고 3만 원 이하라 영수증만으로 충분함"),
    (7, "② 다양성 · ③ 결합", "괄호형 영수증 서식과 처방전", OK, "괄호형 서식에서도 금액을 읽어 검산이 맞고 처방전 조건이 맞음"),
    (8, "② 다양성", "한방 표 서식 영수증", OK, "한방 서식 영수증의 검산이 맞고 3만 원 이하 통원임"),
    (9, "② 다양성", "한방 괄호형 서식 영수증", OK, "한방 괄호형 서식 영수증의 검산이 맞고 3만 원 이하 통원임"),
    (10, "② 다양성", "괄호형 약제비 영수증", OK, "괄호형 약제비 영수증의 검산이 맞고 3만 원 이하임"),
    (11, "② 다양성 · ④ 저품질", "간이 서식, 인쇄 후 스캔", OK, "간이 서식에는 영수증 번호 칸이 없지만 금액 검산이 맞고 3만 원 이하임"),
    (12, "② 다양성 · ③ 결합", "영수증과 납입확인서", OK, "납입확인서는 판정 근거로 쓰지 않고 영수증만으로 3만 원 이하 통원 기준을 충족함"),
    (14, "③ 결합", "병원 영수증, 처방전, 약국 영수증", OK, "약국 영수증은 요양기관이 달라도 정상이고 처방전 조건이 맞음"),
    (17, "③ 결합", "서류 4종이 한 파일에 섞임", OK, "영수증과 세부내역서 금액이 같고 처방전과 통원확인서 조건이 맞음"),
    (19, "④ 저품질", "본인부담금 칸이 흐림", OK, "흐린 칸을 포함해 검산이 맞고 처방전 조건이 맞음"),
    (20, "④ 저품질", "구긴 영수증", OK, "구김이 있어도 금액을 읽어 검산이 맞고 3만 원 이하 통원임"),
    (24, "③ 결합 · ⑤ 함정", "세부내역서와 영수증 금액 불일치", ("보완 요청", "서류 불일치", [], ["비급여 합계", "진료비 총액"]),
     "세부내역서 비급여 합계 108,000원이 영수증 150,000원보다 42,000원 적고 총액도 다름"),
    (25, "⑤ 함정", "세부내역서 환자 이름이 다름", ("보완 요청", "서류 불일치", [], ["환자 이름"]),
     "세부내역서의 환자 이름이 영수증과 다름"),
    (26, "⑤ 함정", "3만 원 초과인데 처방전 없음", ("보완 요청", "서류 누락", ["처방전"], []),
     "환자부담 총액 54,200원으로 3만 원을 넘는데 처방전이나 증빙이 없음"),
    (27, "⑤ 함정", "재발행 영수증 중복 제출", ("보완 요청", "중복 제출", [], []),
     "요양기관과 영수증 번호가 같은 영수증이 두 장 제출됨"),
    (28, "⑤ 함정", "영수증 없이 기타 문서만", ("보완 요청", "서류 누락", ["진료비 영수증"], []),
     "카드 전표 같은 기타 문서만 있고 진료비 영수증이 없음"),
    (29, "③ 결합 · ⑤ 함정", "상한액 초과금이 있는 정상 입원", OK, "상한액 초과금을 빼고 계산하면 환자부담 총액이 맞고 필요한 서류가 있음"),
    (30, "⑤ 함정", "총액이 항목 합과 다르게 인쇄됨", ("검토 필요", "읽기 오류", [], []),
     "① 4,200원과 ② 9,800원의 합은 14,000원인데 진료비 총액이 15,000원이라 검산이 맞지 않음"),
    ("시험_10만초과_영수증만", "⑤ 함정", "10만 원 초과인데 증빙·처방전 없음", ("검토 필요", "서류 누락", ["처방전"], []),
     "환자부담 합계가 10만 원을 넘는데 증빙과 처방전이 모두 없음", "차유진", "가상정형외과의원", ["receipt"]),
    ("시험_10만초과_처방전있음", "③ 결합 · ⑤ 함정", "10만 원 초과, 처방전만 있음", ("검토 필요", "서류 누락", [], []),
     "환자부담 합계가 10만 원을 넘는데 진단명이 있는 증빙이 없음. 처방전은 있음", "차유진", "가상정형외과의원",
     ["receipt", "prescription"]),
    ("시험_비뇨의학과_증빙있음", "③ 결합 · ⑤ 함정", "진료과 예외(비뇨의학과), 증빙 있음", OK,
     "비뇨의학과는 금액과 상관없이 증빙 조건을 보며 진단명이 있는 증빙이 있음", "홍지호", "가상정형외과의원",
     ["receipt", "prescription", "visit_cert", "itemized_bill"]),
    ("시험_피부과_증빙없음", "⑤ 함정", "진료과 예외(피부과), 증빙 없음", ("검토 필요", "서류 누락", [], []),
     "피부과는 금액과 상관없이 증빙 조건을 보는데 증빙이 없음", "김가온", "가상내과의원", ["receipt"]),
    ("시험_입원정상", "③ 결합", "입원, 세부내역서와 진단서 있음", OK,
     "입원 기준에 필요한 세부내역서와 진단서가 있음", "민서준", "가상병원", ["receipt", "itemized_bill", "diagnosis"]),
    ("시험_입원소액_확인서", "③ 결합", "50만 원 이하 입원, 입퇴원확인서", OK,
     "50만 원 이하 입원이라 진단명이 있는 확인서로 충분하고 세부내역서가 있음", "한우주", "가상병원",
     ["receipt", "itemized_bill", "visit_cert"]),
    ("시험_입원_영수증만", "⑤ 함정", "입원인데 영수증만", ("보완 요청", "서류 누락", ["세부내역서", "진단서"], []),
     "입원인데 세부내역서와 진단서가 없음", "민서준", "가상병원", ["receipt"]),
    ("시험_입원고액_확인서만", "③ 결합 · ⑤ 함정", "50만 원 초과 입원, 진단서 없음", ("보완 요청", "서류 누락", ["진단서"], []),
     "환자부담 합계가 50만 원을 넘는 입원이라 진단서가 필요한데 없음", "배서윤", "가상종합병원",
     ["receipt", "itemized_bill"]),
    ("시험_이슈_영수증_빈페이지", "④ 저품질 · ⑤ 함정", "스캔 묶음에 빈 페이지가 섞임", OK,
     "빈 페이지는 건너뛰고 영수증만으로 3만 원 이하 통원 기준을 충족함", "김가온", "가상내과의원", ["receipt"]),
    (31, "④ 저품질 · ③ 결합", "case_03 영수증·처방전 12도 기울임", OK,
     "환자부담 총액 50,000원이 3만 원을 넘지만 처방전의 질병분류기호 M54가 있어 심사 진행. 기울임 변형에서도 서류 간 이름·기관과 금액 근거가 같다"),
    (32, "④ 저품질 · ③ 결합", "case_17 영수증 묶음 좌측 그림자", OK,
     "환자부담 총액 122,200원이 10만 원을 넘고 처방전·통원확인서가 있어 심사 진행. 그림자 변형에서도 필요한 서류와 요양기관 근거가 같다"),
    (33, "④ 저품질 · ⑤ 함정", "case_26 저해상도·노이즈 확대", ("보완 요청", "서류 누락", ["처방전"], []),
     "환자부담 총액 54,200원이 3만 원을 넘는데 처방전이 없어 보완 요청. 저해상도 변형에서도 영수증 금액과 누락 서류 규칙은 원본과 같다"),
    (34, "⑤ 함정", "처방전 환자 이름 불일치", ("보완 요청", "서류 불일치", [], ["환자 이름"]),
     "영수증 환자 안소율과 처방전 환자 안소연이 달라 서류 불일치로 보완 요청"),
    (35, "⑤ 함정", "재발행 영수증과 다른 영수증 중복", ("보완 요청", "중복 제출", [], []),
     "같은 영수증 번호가 발행일만 다른 재발행본과 함께 제출되어 중복 제출로 보완 요청"),
    (36, "⑤ 함정", "환자부담 정확히 30,000원", OK,
     "환자부담 총액이 정확히 30,000원으로 경계 이하이며 영수증만으로 심사 진행"),
    (37, "⑤ 함정", "입원 세부내역서 비급여·총액 불일치", ("보완 요청", "서류 불일치", [], ["비급여 합계", "진료비 총액"]),
     "입원 영수증과 세부내역서의 비급여 합계와 진료비 총액이 달라 서류 불일치로 보완 요청"),
]


def load(number):
    return json.loads((ROOT / "answers" / f"case_{number:02d}.json").read_text(encoding="utf-8"))


def first_values(answer):
    name = answer["documents"][0]["file_name"]
    return {f["key"]: f["value"] for f in answer["fields"] if f["file_name"] == name}


def make_pdf(answer, path):
    # Minimal image-only PDF writer: keeps synthetic source images intact without
    # requiring a native PDF package in the execution environment.
    objects = []
    pages = []
    for doc in answer["documents"]:
        image = ROOT / "cases" / answer["case_id"] / f"{doc['file_name']}.jpg"
        from PIL import Image
        im = Image.open(image).convert("RGB")
        import io
        buf = io.BytesIO(); im.save(buf, format="JPEG", quality=90); data = buf.getvalue()
        w, h = im.size
        img_obj = len(objects) + 1
        objects.append((f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"))
        content = f"q\n{w} 0 0 {h} 0 0 cm\n/Im{len(pages)+1} Do\nQ\n".encode()
        content_obj = len(objects) + 1; objects.append((f"<< /Length {len(content)} >>\nstream\n".encode()+content+b"endstream"))
        page_obj = len(objects) + 1; objects.append((f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 {w} {h}] /Resources << /XObject << /Im{len(pages)+1} {img_obj} 0 R >> >> /Contents {content_obj} 0 R >>".encode()))
        pages.append(page_obj)
    pages_obj = len(objects)+1; objects.append((f"<< /Type /Pages /Kids [{' '.join(str(p)+' 0 R' for p in pages)}] /Count {len(pages)} >>".encode()))
    catalog_obj = len(objects)+1; objects.append((f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()))
    raw = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(raw)); raw.extend(f"{i} 0 obj\n".encode()); raw.extend(obj); raw.extend(b"\nendobj\n")
    xref=len(raw); raw.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]: raw.extend(f"{off:010d} 00000 n \n".encode())
    raw.extend(f"trailer\n<< /Size {len(objects)+1} /Root {catalog_obj} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    # Patch page parent references now that pages_obj is known.
    raw = raw.replace(b"/Parent 0 0 R", f"/Parent {pages_obj} 0 R".encode())
    path.write_bytes(raw)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    cases, rows = [], []
    for index, entry in enumerate(SETS, 1):
        source, kind, point, (decision, cause, missing, mismatches), reason = entry[:5]
        file_name = f"{TEAM}_최종제출_set{index:02d}.pdf"
        if isinstance(source, int):
            answer = load(source)
            values = first_values(answer)
            if answer["documents"][0]["type"] == "other":
                values = {}
            types = [d["type"] for d in answer["documents"]]
            make_pdf(answer, OUT / file_name)
            origin = answer["case_id"]
        else:
            values = {"patient_name": entry[5], "provider_name": entry[6]}
            types = entry[7]
            source_pdf = TEST_DIR / f"{source}.pdf"
            if source_pdf.exists():
                shutil.copyfile(source_pdf, OUT / file_name)
            else:
                # The original 29-file submission already contains this virtual
                # test PDF; retain it when the source fixture is not checked in.
                old_pdf = OUT / file_name
                if not old_pdf.exists():
                    raise FileNotFoundError(source_pdf)
            origin = source
        documents = [DOC_NAMES[t] for t in types]
        cases.append({
            "case_id": f"set{index:02d}",
            "file": file_name,
            "documents": documents,
            "answer": {
                "patient_name": values.get("patient_name", ""), "provider_name": values.get("provider_name", ""),
                "decision": decision, "cause": cause, "reason": reason,
                "missing_documents": missing, "mismatches": mismatches,
            },
        })
        rows.append((file_name, origin, documents, kind, point, decision))
    answer_sheet = {
        "task": "실손보험 청구 서류 검증 (가상)",
        "unit": "청구 1건 = 파일 1개(서류 묶음 PDF) = 판정 1건",
        "output_keys": OUTPUT_KEYS,
        "decision_values": DECISIONS,
        "cases": cases,
    }
    (OUT / f"{TEAM}_최종제출_answer.json").write_text(
        json.dumps(answer_sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return answer_sheet, rows


def build_types(rows, path):
    book = openpyxl.load_workbook(TYPES_TEMPLATE)
    sheet = book["유형표"]
    sheet.delete_rows(2, sheet.max_row)
    row = 2
    for file_name, origin, documents, kind, point, decision in rows:
        for page, document in enumerate(documents, 1):
            cells = [row - 1, file_name, page, origin, document, kind, point, decision]
            for column, value in enumerate(cells, 1):
                sheet.cell(row=row, column=column, value=value)
            row += 1
    book.save(path)
    return row - 2


def main():
    answer_sheet, rows = build()
    documents = build_types(rows, OUT / f"{TEAM}_최종제출_유형표.xlsx")
    decisions = {}
    for case in answer_sheet["cases"]:
        decisions[case["answer"]["decision"]] = decisions.get(case["answer"]["decision"], 0) + 1
    print(f"파일 {len(rows)}개, 문서 {documents}건, 판정 {decisions}")


if __name__ == "__main__":
    main()
