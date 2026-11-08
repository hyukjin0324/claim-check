"""최종 설계서 DOCX를 기존 미션 2 양식의 스타일로 생성한다."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "submission/mission2/컴학감동_미션2_설계서.docx"
OUT = ROOT / "submission/final/컴학감동_최종제출_설계서.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
def q(name): return f"{{{W}}}{name}"

def run(text, bold=False, size=19, color=None):
    r = Element(q("r")); rp = SubElement(r, q("rPr"))
    fonts = SubElement(rp, q("rFonts")); fonts.set(q("ascii"), "Arial Unicode MS"); fonts.set(q("hAnsi"), "Arial Unicode MS"); fonts.set(q("eastAsia"), "Arial Unicode MS"); fonts.set(q("cs"), "Arial Unicode MS")
    if bold: SubElement(rp, q("b"))
    sz = SubElement(rp, q("sz")); sz.set(q("val"), str(size))
    lang = SubElement(rp, q("lang")); lang.set(q("val"), "ko-KR"); lang.set(q("eastAsia"), "ko-KR")
    if color:
        c = SubElement(rp, q("color")); c.set(q("val"), color)
    t = SubElement(r, q("t")); t.text = text
    return r

def para(text="", style=None, bold=False, size=19, color=None, align=None):
    p = Element(q("p")); pp = SubElement(p, q("pPr"))
    if style:
        ps = SubElement(pp, q("pStyle")); ps.set(q("val"), style)
    sp = SubElement(pp, q("spacing")); sp.set(q("before"), "40"); sp.set(q("after"), "100")
    if align:
        jc = SubElement(pp, q("jc")); jc.set(q("val"), align)
    p.append(run(text, bold=bold, size=size, color=color))
    return p

def cell(text, width, shade=False, bold=False, size=17):
    tc = Element(q("tc")); tcp = SubElement(tc, q("tcPr"))
    tw = SubElement(tcp, q("tcW")); tw.set(q("type"), "dxa"); tw.set(q("w"), str(width))
    if shade:
        sh = SubElement(tcp, q("shd")); sh.set(q("val"), "clear"); sh.set(q("color"), "auto"); sh.set(q("fill"), "EAE6FF")
    va = SubElement(tcp, q("vAlign")); va.set(q("val"), "center")
    tc.append(para(str(text), bold=bold, size=size))
    return tc

def table(headers, rows, widths=None):
    cols = len(headers); widths = widths or [9000 // cols] * cols
    tbl = Element(q("tbl")); tp = SubElement(tbl, q("tblPr")); tw = SubElement(tp, q("tblW")); tw.set(q("type"), "dxa"); tw.set(q("w"), str(sum(widths)))
    layout = SubElement(tp, q("tblLayout")); layout.set(q("type"), "fixed")
    borders = SubElement(tp, q("tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        x = SubElement(borders, q(edge)); x.set(q("val"), "single"); x.set(q("sz"), "4"); x.set(q("color"), "D1D1D8")
    grid = SubElement(tbl, q("tblGrid"))
    for w in widths:
        g = SubElement(grid, q("gridCol")); g.set(q("w"), str(w))
    for ri, row in enumerate([headers] + rows):
        tr = SubElement(tbl, q("tr"))
        for i, value in enumerate(row): tr.append(cell(value, widths[i], shade=(ri == 0 or i == 0), bold=(ri == 0), size=16 if ri else 16))
    return tbl

def build_body():
    body = Element(q("body"))
    body.append(para("미션 2 최종 제출 설계서", style="Title", bold=True, size=32, align="center"))
    body.append(para("- 컴학감동 실손보험 청구 서류 검증 워크플로우 -", style="Heading1", size=22, align="center"))
    body.append(table(["항목", "내용"], [
        ["팀명", "컴학감동"], ["주제", "실손보험 청구 서류 1차 검증"],
        ["워크플로우", "컴학감동_미션2_실손보험 청구 서류 검증"], ["기준 구조", "Studio 설정 #13 (Classify에 blank 포함)"],
        ["유즈케이스", "U129"], ["출처", "공식 서식에 가상 값을 채운 문서. 실제 환자 정보·실제 진료 서류는 사용하지 않음."],
    ], [2100, 6900]))
    body.append(para("1. 목표와 범위", style="Heading1", bold=True, size=24))
    body.append(para("청구 서류 묶음에서 영수증 금액을 검산하고, 중복·서류 간 불일치·필요 서류 누락을 찾아 심사 진행, 보완 요청, 검토 필요 중 하나로 1차 분류한다. 보험금 지급 여부, 의학적 판단, 보험사기 판단은 하지 않는다."))
    body.append(para("2. 워크플로우 구조와 노드 역할", style="Heading1", bold=True, size=24))
    body.append(para("설정 #13의 흐름은 Parse → Classify(blank 포함) → Extract 4개 → 병합-1 → 청구_판정 → 정리 노드 지시-1·2·3 → 보완_요청_문구 / 담당자_확인_메모다. blank는 어떤 노드에도 연결하지 않는다."))
    body.append(table(["노드", "역할", "이유"], [
        ["Parse", "OCR(force), 좌표 True, 표 병합 False로 HTML·text를 만든다.", "금액 칸과 표의 위치를 보존해 후속 추출이 같은 칸을 보게 한다."],
        ["Classify", "receipt, itemized_bill, prescription, evidence, Other, blank로 낱장(PAGE) 분류한다.", "문서 종류별 추출 경로를 나누고 빈 페이지가 전체 판정을 막지 않게 한다."],
        ["영수증_추출", "환자·기관·진료 정보와 ①~⑤, 총액을 구조화한다.", "A/B 검산과 환자부담 합계의 기준값이다."],
        ["세부내역서_추출", "본인부담·공단·전액본인부담·비급여·총액 합계와 신원을 추출한다.", "영수증과 서류 금액·이름·기관을 비교한다."],
        ["처방전_추출", "환자·기관·발행일·질병분류기호를 추출한다.", "통원 필요 서류 조건을 판단한다."],
        ["증빙_추출", "문서 종류·환자·기관·진단명을 추출한다.", "증빙·진단서 조건을 판단한다."],
        ["병합-1", "네 추출 결과와 미분류_안내 결과를 한 청구 건으로 묶는다.", "판정 노드가 제출된 문서 전체를 한 번에 보게 한다. Other 결과는 근거로 세지 않는다."],
        ["청구_판정", "정해진 순서로 검산·중복·비교·필요 서류를 판단하고 7개 키를 낸다.", "앞 단계 실패가 뒤 단계의 다른 원인으로 덮이지 않게 한다."],
        ["지시-1·2·3", "판정 결과를 후속 분기와 정리용 출력으로 전달한다.", "최종 판정과 고객 안내·담당자 메모를 분리한다."],
        ["보완_요청_문구 / 담당자_확인_메모", "보완 요청 안내문 또는 검토 메모를 200자 이내로 쓴다.", "정답 키와 운영 문구를 분리해 채점 키를 안정적으로 유지한다."],
    ], [2100, 3600, 3300]))
    body.append(para("3. 판정 규칙 순서와 이유", style="Heading1", bold=True, size=24))
    body.append(table(["순서", "규칙", "이유"], [
        ["사전", "영수증이 없으면 읽기 오류가 아니라 서류 누락으로 보완 요청. Other는 근거로 세지 않음.", "문서 자체가 없는 경우와 읽지 못한 경우를 구분한다."],
        ["1 읽기 점검", "빈 ③·④·⑤는 0으로 계산하고 A=①+②+③+④, B=①-⑤+③+④를 두 수씩 적어 총액과 비교. 다르면 즉시 검토 필요/읽기 오류.", "잘못 읽은 값으로 중복·서류 비교를 하면 거짓 불일치가 되므로 가장 먼저 확정한다."],
        ["2 중복", "요양기관과 영수증 번호가 같은 영수증이 2장 이상이면 보완 요청/중복 제출.", "중복 금액을 합산하는 오류를 막는다."],
        ["3 서류 비교", "세부내역서의 다섯 합계와 이름·기관을 영수증과 비교. 다르면 보완 요청/서류 불일치.", "검산을 통과한 확정값끼리만 비교한다."],
        ["4 필요 서류", "입원 기준, 진료과 예외, 10만 원 초과, 처방전·증빙 조건을 위에서부터 처음 맞는 줄만 적용한다.", "금액·진료과·서류 조합의 우선순위를 고정해 판정 흔들림을 줄인다."],
        ["5 최종", "1~4단계에서 걸리지 않으면 심사 진행. 진행이면 목록 두 개는 반드시 [].", "누락 조건을 통과로 해석하는 문제를 막는다."],
    ], [1400, 4700, 2900]))
    body.append(para("4. 설정 #4~#13 변경 이력", style="Heading1", bold=True, size=24))
    body.append(table(["설정", "변경", "전 결과", "후 결과"], [
        ["#4", "통원 규칙을 처음 맞는 한 줄만 적용, 10만 원 기준을 앞으로 이동", "13건 중 6건 오판", "후속 규칙 충돌을 드러냄"],
        ["#5", "5단계 문장 교체, reason을 decision보다 먼저, 누락 모두 기록", "#4의 통과 오판", "39회 중 38회 일치; set04 1회 오판"],
        ["#6", "reason 첫머리에 읽기·중복·비교 결과를 먼저 기록", "set04·읽기 오류 흔들림", "39회 중 38회 일치; set02 1회 오판"],
        ["#7", "처방전·증빙 중 하나라도 맞으면 3번 줄을 적용하지 않음", "3번 줄 오적용", "18개×3회에서 기존 건 안정화; 읽기 오류·Other 약점 확인"],
        ["#8", "검산을 두 수씩 쓰고 불일치면 즉시 읽기 오류", "계산·판정 흔들림", "Other 외 17개 85회 일치"],
        ["#9", "미분류_안내를 병합-1에 연결, 영수증 부재·Other 규칙 명시", "Other만 판정 없음", "18개×5회 90회 일치"],
        ["#10", "Classify에 blank 추가, 연결 없음", "빈 페이지가 OCR 실패로 전체 실패", "19개×2회 38회 일치"],
        ["#11", "최종 데이터셋 ①~⑤로 확대", "5건 중심", "29세트·56문서로 확장"],
        ["#12", "정답지·유형표·후속 노드 정리", "이름·기관 미검증", "최종 제출 형식과 유형표 완성"],
        ["#13", "#5 청구_판정 프롬프트를 제출본에 반영", "초기 프롬프트 규칙", "1회 29세트에서 28/29 키 일치; set04가 유일 오판"],
    ], [850, 2850, 2450, 2850]))
    body.append(para("5. 예외 처리", style="Heading1", bold=True, size=24))
    body.append(table(["예외", "처리"], [
        ["빈 페이지(blank)", "글자가 없거나 거의 없으면 blank로 분류하고 연결하지 않는다. 같은 청구의 영수증 판정을 막지 않는다."],
        ["읽기 오류(검산)", "A 또는 B가 총액과 다르면 즉시 검토 필요/읽기 오류. 이후 중복·서류 비교·필요 서류를 원인으로 바꾸지 않는다."],
        ["기타 문서만", "Other→미분류_안내→병합-1로 보내되 판정 근거로 세지 않는다. 영수증이 없으므로 보완 요청/서류 누락/진료비 영수증."],
        ["진료과 예외", "산부인과·항문외과·비뇨기과·비뇨의학과·피부과는 금액과 무관하게 증빙 조건을 먼저 본다."],
        ["병원·약국 차이", "영수증의 요양기관 종류와 무관하게 영수증은 영수증으로 읽고, 약국 영수증은 약제비 총액과 중복 여부를 같은 규칙으로 검산한다. 서로 다른 기관의 처방·약국 영수증은 중복으로 합치지 않는다."],
        ["인용 표시 정리", "청구_판정의 인용 표시는 채점 키가 아니므로 지시-1·2·3에서 정리한다. 최종 키 7개는 `키: 값` 한 줄 형식을 유지한다."],
    ], [2200, 6800]))
    body.append(para("6. 한계와 미사용 기능", style="Heading1", bold=True, size=24))
    body.append(table(["항목", "확인 내용"], [
        ["총액 칸이 빈 영수증", "서식의 계산식 때문에 추출 단계가 총액을 채우는 사례가 있어, 설명만으로 빈 칸을 확정하지 못했다. 최종 데이터셋 함정 케이스에서는 제외했다."],
        ["흐린 문서", "저품질·흐림 칸은 표본에서 통과한 사례도 있지만 OCR과 LLM 계산에 의존하므로 일반화하지 않는다."],
        ["set04", "초기 #13 결과는 비급여 ④를 0으로 읽어 A=14,000으로 계산하고 검토 필요/읽기 오류가 됐다. 원본에는 선택항목 50,000원+제증명 3,000원=④ 53,000원이 있어 A=67,000, B=57,200이 정답이다. 비급여 추출 지시를 보강한 재실행에서 53,000·심사 진행으로 교정됐다."],
        ["Validate 미사용", "합계식의 Red 결과가 판정에 안정적으로 반영되는지 시험하지 못했고, 코드 노드 없이 추가하면 정상 건을 막을 위험이 있어 제출 구조에는 넣지 않았다."],
    ], [2200, 6800]))
    body.append(para("7. 데이터셋과 출처", style="Heading1", bold=True, size=24))
    body.append(table(["구분", "건수"], [
        ["전체 세트", "29개"], ["판정: 심사 진행", "18개"], ["판정: 보완 요청", "7개"], ["판정: 검토 필요", "4개"],
        ["문서 장수", "56건"], ["문서 유형", "진료비 영수증 26, 처방전 9, 세부내역서 8, 통원확인서 4, 약제비 영수증 3, 기타 문서 2, 진단서 2, 간이 영수증 1, 납입확인서 1"],
        ["유형 구성", "① 단순, ② 양식·문맥 다양성, ③ 문서 결합, ④ 저품질, ⑤ 예외·함정 모두 포함"],
        ["출처 칸", "공식 서식에 팀이 만든 가상 값을 채운 재구성 문서. 실제 환자 정보·실제 진료 서류·API 키는 사용하지 않음."],
    ], [2600, 6400]))
    body.append(para("8. 실행 정확도와 검증 범위", style="Heading1", bold=True, size=24))
    body.append(para("확인된 수치만 기록한다. 설정 #13의 전체 1회 실행은 29세트 중 decision/cause/missing_documents/mismatches 키가 28/29 일치했고, set04가 유일한 불일치였다. set04는 추출 지시 보강 후 53,000원으로 교정됐다. `scripts/score_studio.py`의 2회 전체 실행 키별 일치율은 원시 content 결과 파일이 저장소에 없어 산출하지 않았으며, 미실행 수치를 추측해 기재하지 않는다. 이름·기관 정답은 28세트에 명시되고, 기타 문서만인 set18은 빈 값이 정답이다."))
    body.append(para("9. 재현·운영 메모", style="Heading1", bold=True, size=24))
    body.append(para("최종 데이터셋 파일명은 `컴학감동_최종제출_set01.pdf`부터 `set29.pdf`까지다. Studio에서 실행할 때 설정 번호와 파일 목록을 확인하고, 결과를 정답지의 7개 키와 비교한다. 게시·결제·삭제·실제 서류 업로드는 이 설계 범위에 포함하지 않는다."))
    sect = SubElement(body, q("sectPr")); pg = SubElement(sect, q("pgSz")); pg.set(q("w"), "9026"); pg.set(q("h"), "12730")
    mar = SubElement(sect, q("pgMar")); mar.set(q("top"), "720"); mar.set(q("right"), "720"); mar.set(q("bottom"), "720"); mar.set(q("left"), "720")
    return body

def main():
    document = Element(q("document"))
    document.append(build_body())
    xml = tostring(document, encoding="utf-8", xml_declaration=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(TEMPLATE) as zin, ZipFile(OUT, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml": zout.writestr(item, xml)
            else: zout.writestr(item, zin.read(item.filename))
    print(OUT)

if __name__ == "__main__": main()
