"""미션 2 제출 파일을 만든다. 데이터셋 PDF, 정답지, 유형표, 설계서.

필요: pip install pymupdf openpyxl python-docx
실행: python3 scripts/export_mission2.py <템플릿 폴더>
"""
import copy
import json
import sys
from pathlib import Path

import docx
import docx.table
import docx.text.paragraph
import fitz
import openpyxl
from docx.shared import RGBColor

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "submission" / "mission2"
TEAM = "컴학감동"
OUTPUT_KEYS = ["patient_name", "provider_name", "decision", "cause", "reason", "missing_documents", "mismatches"]
DECISIONS = ["심사 진행", "보완 요청", "검토 필요"]
DOC_NAMES = {"receipt": "진료비 영수증", "prescription": "처방전", "visit_cert": "통원확인서", "itemized_bill": "세부내역서"}
# 설정 #3을 세트마다 1번 돌린 결과. Studio를 다시 돌리면 여기를 고친다.
TEST_RUNS = {
    "A": ("심사 진행", "없음", [], []),
    "B": ("심사 진행", "없음", [], []),
    "C": ("보완 요청", "서류 누락", ["처방전"], []),
    "D": ("보완 요청", "서류 불일치", [], ["비급여 합계", "진료비 총액"]),
    "E": ("보완 요청", "중복 제출", [], []),
}
TEST_POINTS = {"A": "영수증만 낸 3만 원 이하 통원", "B": "처방전이 있는 3만 원 초과 통원", "C": "처방전이 빠진 3만 원 초과 통원",
               "D": "세부내역서와 영수증의 금액이 다름", "E": "같은 영수증 2장"}
TEST_LINES = [
    "방법: 워크플로우 설정 #3으로 세트 5개를 1번씩 실행해 decision, cause, missing_documents, mismatches를 정답지와 비교함. reason은 문장이 달라도 되는 값이라 글자 비교에서 뺌",
    "결과: 5개 세트 모두 위 네 값이 일치함. 세트가 적고 1번씩만 돌렸으므로 정확도로 내세우지 않음",
    "시험하며 고친 점: 처방전이 있는 건을 잘못 판정해 프롬프트를 고침 / 영수증만으로 충분한 건을 보완 요청으로 판정해 '걸리는 조건이 없으면 심사 진행' 규칙을 추가함 / 같은 서식 영수증 2장이 한 문서로 묶여 중복을 놓쳐 분할을 낱장 분리로 바꿈",
    "아직 확인하지 못한 점: 입원·진료과 예외 시험 파일 6건은 이전 설정 #1에서만 맞았고 설정 #3으로는 다시 돌리지 않음 / 같은 파일 반복 실행 시 판정 유지 / 읽기 오류와 기타 문서 건 / 여러 쪽 세부내역서의 낱장 분리",
    "최종 제출 전 할 일: 위 항목 시험, 채점 스크립트로 키별 일치율 측정, Validate 규칙 판정 추가",
]
SOURCE = "출처: 국민건강보험 요양급여의 기준에 관한 규칙 별지 서식, 의료법 시행규칙 처방전·진단서 서식, 손해보험협회 청구서류 표준안. 문서는 위 공식 서식에 팀이 만든 가상 값을 채워 재구성했고, 실제 환자 정보는 없음"
CASES = [
    {"id": "A", "number": 1, "decision": "심사 진행", "cause": "없음",
     "reason": "환자부담 총액 4,200원의 3만 원 이하 통원으로 영수증만으로 충분하고, 금액 검산이 맞음",
     "missing": [], "mismatches": [],
     "rows": [("① 단순", "기본 추출과 금액 검산")]},
    {"id": "B", "number": 3, "decision": "심사 진행", "cause": "없음",
     "reason": "환자부담 총액 50,000원으로 질병분류기호가 있는 처방전이 필요하며 제출됨. 환자와 요양기관이 일치함",
     "missing": [], "mismatches": [],
     "rows": [("③ 결합", "한 PDF에 섞인 서류 2종 분류"), ("① 단순 · ③ 결합", "질병분류기호를 읽어 3만 원 초과 기준 확인")]},
    {"id": "C", "number": 26, "decision": "보완 요청", "cause": "서류 누락",
     "reason": "환자부담 총액 54,200원으로 3만 원을 넘는데 질병분류기호가 적힌 처방전이나 진단명이 있는 증빙이 없음",
     "missing": ["처방전"], "mismatches": [],
     "rows": [("⑤ 예외", "서류가 빠지면 추측하지 않고 보완 요청")]},
    {"id": "D", "number": 24, "decision": "보완 요청", "cause": "서류 불일치",
     "reason": "영수증은 검산이 맞지만 세부내역서 비급여 합계가 108,000원으로 영수증 150,000원보다 42,000원 적고 총액도 다름",
     "missing": [], "mismatches": ["비급여 합계", "진료비 총액"],
     "rows": [("③ 결합", "영수증 금액 검산 뒤 서류 비교"), ("③ 결합", "서류 4종 분류"), ("③ 결합", "진단명이 있는 증빙 인식"),
              ("⑤ 예외", "세부내역서와 영수증의 금액 불일치 탐지")]},
    {"id": "E", "number": 27, "decision": "보완 요청", "cause": "중복 제출",
     "reason": "요양기관과 영수증 번호가 같은 영수증이 두 장 제출됨",
     "missing": [], "mismatches": [],
     "rows": [("③ 결합", "같은 종류 서류 2장 처리"), ("⑤ 예외", "재발행 영수증을 중복으로 판정")]},
]


def load(number):
    return json.loads((ROOT / "answers" / f"case_{number:02d}.json").read_text(encoding="utf-8"))


def values(answer, doc):
    return {f["key"]: f["value"] for f in answer["fields"] if f["file_name"] == doc["file_name"]}


def make_pdf(answer, path):
    pdf = fitz.open()
    for doc in answer["documents"]:
        image = ROOT / "cases" / answer["case_id"] / f"{doc['file_name']}.jpg"
        with fitz.open(image) as picture:
            rect = picture[0].rect
        page = pdf.new_page(width=rect.width, height=rect.height)
        page.insert_image(rect, filename=str(image))
    pdf.save(path, deflate=True)
    return pdf.page_count


def build_answer():
    cases = []
    for case in CASES:
        answer = load(case["number"])
        first = values(answer, answer["documents"][0])
        cases.append({
            "case_id": case["id"],
            "file": f"{TEAM}_미션2_set{CASES.index(case) + 1:02d}.pdf",
            "documents": [DOC_NAMES[d["type"]] for d in answer["documents"]],
            "answer": {
                "patient_name": first["patient_name"], "provider_name": first["provider_name"],
                "decision": case["decision"], "cause": case["cause"], "reason": case["reason"],
                "missing_documents": case["missing"], "mismatches": case["mismatches"],
            },
        })
    return {
        "task": "실손보험 청구 서류 검증 (가상)",
        "unit": "청구 1건 = 파일 1개(서류 묶음 PDF) = 판정 1건",
        "output_keys": OUTPUT_KEYS,
        "decision_values": DECISIONS,
        "cases": cases,
    }


def build_types(template, answer, path):
    book = openpyxl.load_workbook(template)
    sheet = book["유형표"]
    sheet.delete_rows(2, 3)
    row = 2
    for case, entry in zip(CASES, answer["cases"]):
        for page, (kind, purpose) in enumerate(case["rows"], 1):
            cells = [row - 1, entry["file"], page, f"{entry['case_id']} {entry['answer']['patient_name']}",
                     entry["documents"][page - 1], kind, purpose, case["decision"]]
            for column, value in enumerate(cells, 1):
                sheet.cell(row=row, column=column, value=value)
            row += 1
    sheet.delete_rows(row, sheet.max_row)
    book.save(path)
    return row - 2


def set_cell(cell, text):
    paragraph = cell.paragraphs[0]
    for run in paragraph.runs[1:]:
        run._r.getparent().remove(run._r)
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    run.text = text
    run.font.color.rgb = RGBColor(0, 0, 0)
    for extra in cell.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)


def set_paragraph(paragraph, text):
    for run in paragraph.runs[1:]:
        run._r.getparent().remove(run._r)
    paragraph.runs[0].text = text
    paragraph.runs[0].font.color.rgb = RGBColor(0, 0, 0)


def fill_rows(table, rows):
    while len(table.rows) < len(rows) + 1:
        table._tbl.append(copy.deepcopy(table.rows[-1]._tr))
    for row, values_ in zip(table.rows[1:], rows):
        for cell, text in zip(row.cells, values_):
            set_cell(cell, text)
    for row in list(table.rows)[len(rows) + 1:]:
        table._tbl.remove(row._tr)


def add_test_section(document):
    heading = next(p for p in document.paragraphs if p.text.strip().startswith("4."))
    source = document.tables[3]
    last = source._tbl
    new_heading = copy.deepcopy(heading._p)
    last.addnext(new_heading)
    set_paragraph(docx.text.paragraph.Paragraph(new_heading, heading._parent), "5. 테스트 결과")
    new_table = copy.deepcopy(source._tbl)
    new_heading.addnext(new_table)
    table = docx.table.Table(new_table, source._parent)
    for cell, text in zip(table.rows[0].cells, ["세트 · 확인할 점", "정답 (decision / cause)", "실행 결과"]):
        set_cell(cell, text)
    rows = []
    for case, entry in zip(CASES, build_answer()["cases"]):
        answer = entry["answer"]
        run = TEST_RUNS[case["id"]]
        expected = (answer["decision"], answer["cause"], answer["missing_documents"], answer["mismatches"])
        if run != expected:
            raise SystemExit(f"{entry['file']}: 실행 결과 {run}, 정답 {expected}")
        number = entry["file"].rsplit("_", 1)[1].removesuffix(".pdf")
        rows.append((f"{number} {TEST_POINTS[case['id']]}", f"{answer['decision']} / {answer['cause']}", "일치"))
    fill_rows(table, rows)
    body = next(p for p in document.paragraphs if p.text.startswith("업무:"))
    previous = new_table
    for line in TEST_LINES:
        paragraph = copy.deepcopy(body._p)
        previous.addnext(paragraph)
        set_paragraph(docx.text.paragraph.Paragraph(paragraph, body._parent), line)
        previous = paragraph


def build_design(template, path):
    document = docx.Document(template)
    tables = document.tables
    for row, text in zip(tables[0].rows, [
        TEAM, "실손보험 청구 서류 검증", f"{TEAM}_미션2_실손보험 청구 서류 검증", "U129",
        "청구서·계약 대조(Match)를 빼고, 영수증 검산으로 읽기 오류를 먼저 거르며, 필요 서류를 협회 표준안 금액 구간으로 판단하고, 오류 원인을 나눔. 최종 제출에 Validate 규칙 판정 추가 예정",
    ]):
        set_cell(row.cells[1], text)
    lines = {
        "업무:": "업무: 보상 담당자가 청구 서류를 보고 심사 진행 · 보완 요청 · 검토 필요로 1차 판정",
        "문서:": "문서: 4종 — 진료비 영수증, 세부내역서, 처방전, 통원확인서·진단서 (청구 1건 = PDF 1개). 공식 서식에 가상 값을 채움",
        "선정 이유:": "선정 이유: 건마다 여러 서류의 금액을 눈으로 맞춰야 하고, 잘못 읽은 값과 실제 서류 불일치를 구분하기 어려움",
        "판정 기준:": "판정 기준: 영수증 공식 검산식 / 서류 간 환자·기관·금액 일치 / 협회 표준안의 통원·입원 금액별 필요 서류와 진료과 예외 / 중복 제출",
    }
    for paragraph in list(document.paragraphs):
        text = paragraph.text.strip()
        if text.startswith(("1장 분량", "누가 어떤", "마지막 노드가", "노드를 순서대로", "서류 누락 · 값 불일치")):
            paragraph._p.getparent().remove(paragraph._p)
            continue
        for prefix, line in lines.items():
            if text.startswith(prefix):
                set_paragraph(paragraph, line)
                if prefix == "판정 기준:":
                    source = copy.deepcopy(paragraph._p)
                    paragraph._p.addnext(source)
                    set_paragraph(docx.text.paragraph.Paragraph(source, paragraph._parent), SOURCE)
    fill_rows(tables[1], [
        ("patient_name", "문자열", '영수증 환자 이름. 예: "김가온"'),
        ("provider_name", "문자열", '영수증 요양기관. 예: "가상내과의원"'),
        ("decision", " | ".join(DECISIONS), "세 값 중 하나만"),
        ("cause", "없음 | 읽기 오류 | 서류 불일치 | 서류 누락 | 중복 제출", "다음 행동을 나누는 오류 원인"),
        ("reason", "문자열 (1~2문장)", "판정 근거"),
        ("missing_documents", "문자열 배열", "빠진 서류. 없으면 []"),
        ("mismatches", "문자열 배열", "다른 값 이름. 없으면 []"),
    ])
    fill_rows(tables[2], [
        ("1", "Parse", "스캔과 사진을 읽어야 해서 OCR을 켬"),
        ("2", "Classify", "쪽마다 나눠 서류 종류를 분류 (기타 포함). 같은 영수증 2장을 따로 읽어 중복을 찾기 위함"),
        ("3", "Extract ×4", "서류별 값 추출. 영수증은 검산에 필요한 칸까지"),
        ("4", "Merge", "한 청구의 결과를 합침"),
        ("5", "Instruct(결정)", "검산 → 중복 → 서류 비교 → 필요 서류 순서로 판단하고 출력 키 작성. 판정 값은 세 값으로 제한"),
        ("6", "Instruct ×2", "보완 요청이면 고객 안내문, 검토 필요면 담당자 메모 작성"),
    ])
    fill_rows(tables[3], [
        ("서류 누락", "표준안 기준으로 빠진 서류 이름을 남김", "보완 요청"),
        ("서류끼리 값이 다름", "영수증 검산이 맞을 때만 불일치로 판정", "보완 요청"),
        ("검산이 깨지거나 흐린 칸", "불일치로 단정하지 않고 담당자에게 넘김", "검토 필요"),
        ("같은 영수증 재제출", "기관과 번호가 같으면 중복. 금액은 한 번만 셈", "보완 요청"),
        ("엉뚱한 문서", "기타로 분류하고 영수증으로 쓰지 않음", "보완 요청"),
    ])
    add_test_section(document)
    document.save(path)


def main():
    template = Path(sys.argv[1])
    data = OUT / "데이터셋"
    data.mkdir(parents=True, exist_ok=True)
    pages = 0
    answer = build_answer()
    for case, entry in zip(CASES, answer["cases"]):
        pages += make_pdf(load(case["number"]), data / entry["file"])
    (OUT / f"{TEAM}_미션2_answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = build_types(next(template.glob("*유형표*.xlsx")), answer, OUT / f"{TEAM}_미션2_유형표.xlsx")
    build_design(next(template.glob("*설계서*.docx")), OUT / f"{TEAM}_미션2_설계서.docx")
    documents = sum(len(c["documents"]) for c in answer["cases"])
    print(f"케이스 {len(answer['cases'])}, 문서 {documents}, PDF 쪽 {pages}, 유형표 {rows}줄")


if __name__ == "__main__":
    main()
