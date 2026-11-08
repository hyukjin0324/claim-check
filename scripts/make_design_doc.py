"""최종 설계서 DOCX를 기존 미션 2 양식의 스타일로 생성한다."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.sax.saxutils import escape
import json
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # the checked-in PNG is reused when Pillow is unavailable
    Image = ImageDraw = ImageFont = None

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "submission/mission2/컴학감동_미션2_설계서.docx"
OUT = ROOT / "submission/final/컴학감동_최종제출_설계서.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
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

def make_workflow_diagram(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if Image is None and path.exists():
        return
    if Image is None:
        raise RuntimeError("workflow_diagram.png가 없고 Pillow도 설치되지 않았습니다")
    im = Image.new("RGB", (1800, 560), "white"); d = ImageDraw.Draw(im)
    try: font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 34, index=0)
    except Exception: font = ImageFont.load_default()
    nodes = [(40,180,220,360,"Parse"),(270,180,520,360,"Classify\nblank 포함"),(570,130,900,410,"Extract 4개"),(950,180,1220,300,"판정_근거"),(950,340,1220,490,"청구_판정\n(정리)"),(1270,80,1530,210,"심사 진행"),(1270,270,1530,390,"보완_요청_문구"),(1270,440,1530,560,"담당자_확인_메모")]
    for x1,y1,x2,y2,label in nodes:
        d.rounded_rectangle((x1,y1,x2,y2),radius=24,outline="#4f46e5",width=5,fill="#eef2ff")
        lines=label.split("\n"); yy=(y1+y2)//2-20*(len(lines)-1)
        for line in lines:
            box=d.textbbox((0,0),line,font=font); d.text(((x1+x2-(box[2]-box[0]))//2,yy),line,fill="#111827",font=font); yy+=48
    arrows=[((220,270),(270,270)),((520,270),(570,270)),((900,270),(950,240)),((1085,300),(1085,340)),((1220,415),(1270,145)),((1220,415),(1270,330)),((1220,450),(1270,500))]
    for (x1,y1),(x2,y2) in arrows:
        d.line((x1,y1,x2,y2),fill="#6b7280",width=6)
        import math; a=math.atan2(y2-y1,x2-x1); l=18
        d.polygon([(x2,y2),(x2-l*math.cos(a-0.45),y2-l*math.sin(a-0.45)),(x2-l*math.cos(a+0.45),y2-l*math.sin(a+0.45))],fill="#6b7280")
    d.text((55,45),"설정 #16 제출본 흐름(인용 제거 정리 노드와 결정 분기)",fill="#111827",font=font)
    im.save(path)

def image_para(path, rid, width=8500, height=2600):
    p=Element(q("p")); r=SubElement(p,q("r")); drawing=SubElement(r,q("drawing")); inline=SubElement(drawing,"{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline")
    extent=SubElement(inline,"{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"); extent.set("cx",str(width)); extent.set("cy",str(height))
    graphic=SubElement(inline,"{http://schemas.openxmlformats.org/drawingml/2006/main}graphic"); gd=SubElement(graphic,"{http://schemas.openxmlformats.org/drawingml/2006/main}graphicData"); gd.set("uri","http://schemas.openxmlformats.org/drawingml/2006/picture")
    pic=SubElement(gd,"{http://schemas.openxmlformats.org/drawingml/2006/picture}pic"); nv=SubElement(pic,"{http://schemas.openxmlformats.org/drawingml/2006/picture}nvPicPr"); SubElement(nv,"{http://schemas.openxmlformats.org/drawingml/2006/picture}cNvPr",id="0",name=path.name); SubElement(nv,"{http://schemas.openxmlformats.org/drawingml/2006/picture}cNvPicPr")
    blip=SubElement(SubElement(pic,"{http://schemas.openxmlformats.org/drawingml/2006/picture}blipFill"),"{http://schemas.openxmlformats.org/drawingml/2006/main}blip"); blip.set("{%s}embed"%R,rid); SubElement(pic,"{http://schemas.openxmlformats.org/drawingml/2006/picture}spPr")
    return p

def build_body():
    body = Element(q("body"))
    body.append(para("미션 2 최종 제출 설계서", style="Title", bold=True, size=32, align="center"))
    body.append(para("- 컴학감동 실손보험 청구 서류 검증 워크플로우 -", style="Heading1", size=22, align="center"))
    body.append(table(["항목", "내용"], [
        ["팀명", "컴학감동"], ["주제", "실손보험 청구 서류 1차 검증"],
        ["워크플로우", "컴학감동_미션2_실손보험 청구 서류 검증"], ["기준 구조", "Studio 설정 #16 (판정_근거 → 청구_판정 정리, Classify에 blank 포함)"],
        ["유즈케이스", "U129"], ["출처", "공식 서식에 가상 값을 채운 문서. 실제 환자 정보·실제 진료 서류는 사용하지 않음."],
    ], [2100, 6900]))
    body.append(para("1. 목표와 범위", style="Heading1", bold=True, size=24))
    body.append(para("청구 서류 묶음에서 영수증 금액을 검산하고, 중복·서류 간 불일치·필요 서류 누락을 찾아 심사 진행, 보완 요청, 검토 필요 중 하나로 1차 분류한다. 보험금 지급 여부, 의학적 판단, 보험사기 판단은 하지 않는다."))
    body.append(para("2. 워크플로우 구조와 노드 역할", style="Heading1", bold=True, size=24))
    body.append(para("설정 #16의 흐름은 Parse → Classify(blank 포함) → Extract 4개 → 판정_근거 → 청구_판정(정리) → 심사 진행 / 보완_요청_문구 / 담당자_확인_메모다. blank는 어떤 노드에도 연결하지 않는다. 판정_근거는 기존 프롬프트를 그대로 두고, 청구_판정은 일곱 줄을 옮기며 인용 표시만 제거한다."))
    diagram = ROOT / "submission/final/workflow_diagram.png"; make_workflow_diagram(diagram); body.append(image_para(diagram, "rIdDiagram"))
    body.append(table(["노드", "역할", "이유"], [
        ["Parse", "OCR(force), 좌표 True, 표 병합 False로 HTML·text를 만든다.", "금액 칸과 표의 위치를 보존해 후속 추출이 같은 칸을 보게 한다."],
        ["Classify", "receipt, itemized_bill, prescription, evidence, Other, blank로 낱장(PAGE) 분류한다.", "문서 종류별 추출 경로를 나누고 빈 페이지가 전체 판정을 막지 않게 한다."],
        ["영수증_추출", "환자·기관·진료 정보와 ①~⑤, 총액을 구조화한다.", "A/B 검산과 환자부담 합계의 기준값이다."],
        ["세부내역서_추출", "본인부담·공단·전액본인부담·비급여·총액 합계와 신원을 추출한다.", "영수증과 서류 금액·이름·기관을 비교한다."],
        ["처방전_추출", "환자·기관·발행일·질병분류기호를 추출한다.", "통원 필요 서류 조건을 판단한다."],
        ["증빙_추출", "문서 종류·환자·기관·진단명을 추출한다.", "증빙·진단서 조건을 판단한다."],
        ["판정_근거", "네 Extract 결과를 정해진 순서로 판단하고 인용이 붙은 7개 키를 낸다.", "근거가 있는 원판정을 보존해 검토 가능하게 한다."],
        ["청구_판정", "판정_근거의 일곱 줄과 마지막 decision을 같은 값으로 옮기고 인용 표시를 제거한 뒤 3개 결정으로 분기한다.", "판정과 표시 정리를 분리해 인용 번호가 채점 키를 오염시키지 않게 한다."],
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
    body.append(para("4. 설정 #4~#16 변경 이력", style="Heading1", bold=True, size=24))
    body.append(table(["설정", "변경", "전 결과", "후 결과"], [
        ["#4", "통원 규칙을 처음 맞는 한 줄만 적용, 10만 원 기준을 앞으로 이동", "13건 중 6건 오판", "후속 규칙 충돌을 드러냄"],
        ["#5", "5단계 문장 교체, reason을 decision보다 먼저, 누락 모두 기록", "#4의 통과 오판", "39회 중 38회 일치; set04 1회 오판"],
        ["#6", "reason 첫머리에 읽기·중복·비교 결과를 먼저 기록", "set04·읽기 오류 흔들림", "39회 중 38회 일치; set02 1회 오판"],
        ["#7", "처방전·증빙 중 하나라도 맞으면 3번 줄을 적용하지 않음", "3번 줄 오적용", "18개×3회에서 기존 건 안정화; 읽기 오류·Other 약점 확인"],
        ["#8", "검산을 두 수씩 쓰고 불일치면 즉시 읽기 오류", "계산·판정 흔들림", "Other 외 17개 85회 일치"],
        ["#9", "미분류_안내를 병합-1에 연결, 영수증 부재·Other 규칙 명시", "Other만 판정 없음", "18개×5회 90회 일치"],
        ["#10", "Classify에 blank 추가, 연결 없음", "빈 페이지가 OCR 실패로 전체 실패", "19개×2회 38회 일치"],
        ["#11", "정리 노드 지시-1·2·3 추가, 인용 표시 제거", "판정 본문에 인용 표시가 남음", "후속 출력에서 인용 표시를 제거하고 키 형식을 유지"],
        ["#12", "cap_excess를 상한액 초과금으로 설명하고 검산에서 차감", "상한액 초과금이 환자부담에 섞임", "정상 입원 케이스에서 초과금을 제외한 B 계산"],
        ["#13", "청구_판정 프롬프트에 30,000원 이하, 병원·약국 요양기관, reason 양식 반영", "기관·금액 경계가 모호", "처방전·증빙과 금액 기준을 순서대로 판정"],
        ["#14", "noncovered_total 추출 지시를 명시", "set04 비급여 ④가 0으로 읽힘", "비급여 합계를 재추출하도록 보강"],
        ["#15", "noncovered_total 보강을 반영한 제출 기준 설정", "set04: 14,000원 검산→읽기 오류", "set04: 비급여 53,000원, A=67,000/B=57,200→심사 진행"],
        ["#16", "판정_근거와 청구_판정(정리)으로 분리, 인용 표시 제거", "판정 결과에 【†숫자】가 남고 지시 노드가 분기함", "새 청구_판정에서 같은 7개 키와 decision을 정리하고 결정 분기"],
    ], [850, 2850, 2450, 2850]))
    body.append(para("5. 예외 처리", style="Heading1", bold=True, size=24))
    body.append(table(["예외", "처리", "확인 파일"], [
        ["빈 페이지(blank)", "글자가 없거나 거의 없으면 blank로 분류하고 연결하지 않는다. 같은 청구의 영수증 판정을 막지 않는다.", "set29"],
        ["읽기 오류(검산)", "A 또는 B가 총액과 다르면 즉시 검토 필요/읽기 오류. 이후 중복·서류 비교·필요 서류를 원인으로 바꾸지 않는다.", "set04, set28"],
        ["기타 문서만", "Other→미분류_안내로 보내되 판정 근거로 세지 않는다. 영수증이 없으므로 보완 요청/서류 누락/진료비 영수증.", "set18"],
        ["진료과 예외", "산부인과·항문외과·비뇨기과·비뇨의학과·피부과는 금액과 무관하게 증빙 조건을 먼저 본다.", "set22, set23"],
        ["병원·약국 차이", "약국 영수증은 병원 영수증·처방전과 요양기관이 달라도 정상이고, 같은 기관이 낸 서류끼리만 요양기관을 비교한다.", "set03, set10, set14"],
        ["인용 표시 정리", "판정_근거의 인용을 새 청구_판정(정리)에서 제거한다. 최종 키 7개는 `키: 값` 형식을 유지한다.", "set01~set32"],
    ], [1800, 5400, 1800]))
    body.append(para("6. 한계와 미사용 기능", style="Heading1", bold=True, size=24))
    body.append(table(["항목", "확인 내용"], [
        ["총액 칸이 빈 영수증", "서식의 계산식 때문에 추출 단계가 총액을 채우는 사례가 있어, 설명만으로 빈 칸을 확정하지 못했다. 최종 데이터셋 함정 케이스에서는 제외했다."],
        ["흐린 문서", "글자를 거의 읽을 수 없는 흐린 문서는 OCR에서 글자를 찾지 못해 판정이 나오지 않는다. 최종 데이터셋에서 제외했다"],
        ["set04", "초기 #13 결과는 비급여 ④를 0으로 읽어 A=14,000으로 계산하고 검토 필요/읽기 오류가 됐다. 원본에는 선택항목 50,000원+제증명 3,000원=④ 53,000원이 있어 A=67,000, B=57,200이 정답이다. #15에서 53,000·심사 진행으로 교정됐다."],
        ["set12", "2회째 실행에서 patient_name·provider_name이 빈 값이었지만 decision은 정답이었다. 흐린 칸에서 이름·기관 OCR이 빠진 한계다."],
        ["Validate 미사용", "합계식의 Red 결과가 판정에 안정적으로 반영되는지 시험하지 못했고, 코드 노드 없이 추가하면 정상 건을 막을 위험이 있어 제출 구조에는 넣지 않았다."],
    ], [2200, 6800]))
    body.append(para("7. 데이터셋과 출처", style="Heading1", bold=True, size=24))
    body.append(table(["구분", "건수"], [
        ["전체 세트", "32개 (원본 29 + 저품질 보강 3)"], ["판정: 심사 진행", "20개"], ["판정: 보완 요청", "8개"], ["판정: 검토 필요", "4개"],
        ["문서 장수", "63건"], ["문서 유형", "원본 56건 + 저품질 변형 7건(회전 2, 그림자 4, 저해상도 1)"],
        ["유형 구성", "① 단순, ② 양식·문맥 다양성, ③ 문서 결합, ④ 저품질, ⑤ 예외·함정 모두 포함. set30~32는 case_03·17·26의 변형"],
        ["출처 칸", "공식 서식에 팀이 만든 가상 값을 채운 재구성 문서. 실제 환자 정보·실제 진료 서류·API 키는 사용하지 않음."],
    ], [2600, 6400]))
    body.append(para("8. 실행 정확도와 검증 범위", style="Heading1", bold=True, size=24))
    body.append(para("실행 정확도는 설정 #16으로 32개를 2회 실행한 뒤 `scripts/score_studio.py`가 산출한 키별 일치율만 기록한다. 두 실행 사이 decision이 바뀐 파일 수(흔들림)도 실제 결과에서 계산하며, 실행하지 않은 숫자는 쓰지 않는다. 보완_요청_문구와 담당자_확인_메모는 실행 결과의 원문을 그대로 인용한다."))
    body.append(table(["키", "일치율(64회)"], [["patient_name", "64/64 (100.0%)"], ["provider_name", "64/64 (100.0%)"], ["decision", "64/64 (100.0%)"], ["cause", "64/64 (100.0%)"], ["missing_documents", "64/64 (100.0%)"], ["mismatches", "64/64 (100.0%)"], ["키 전체", "384/384 (100.0%)"], ["decision 흔들림", "0개 파일"]], [3300, 5700]))
    body.append(para("실행 결과 원문 예시 — 보완_요청_문구: ‘누락 서류: 처방전입니다. 현재 확인된 진료비 영수증은 외래 진료이며, 환자부담 총액은 54,200원입니다. 다시 보내주실 서류: 처방전. 제출 기한: 담당자 지정입니다.’ (set32)"))
    body.append(para("실행 결과 원문 예시 — 담당자_확인_메모: ‘- **검토 이유**: 외래 영수증이며 진료과는 피부과, 환자부담총액은 4,200원입니다. 제출 문서만으로는 비교할 세부내역서·처방전·추가 증빙 여부를 확인할 수 없어 검토가 필요합니다.’ (set24)"))
    body.append(table(["검토했지만 쓰지 않은 방법", "이유"], [["Validate", "Red/Green 결과를 판정에 안정적으로 연결하는 검증이 부족해 제출본에서는 미사용"], ["코드 노드", "금액 계산을 코드로 고정하면 OCR 빈 값·서식 변형을 다루는 설명력이 줄어 미사용"], ["판정 노드 하나만 쓰기", "검산·중복·비교·필요 서류를 한 프롬프트에 섞으면 원인 덮어쓰기와 흔들림이 생겨 정리 노드로 분리"], ["Other를 청구_판정에 직접 연결", "카드 전표·수납대장만으로 심사 진행을 내지 않도록 미분류_안내에서 멈춤"]], [3000, 6000]))
    body.append(para("9. 재현·운영 메모", style="Heading1", bold=True, size=24))
    body.append(para("최종 데이터셋 파일명은 `컴학감동_최종제출_set01.pdf`부터 `set32.pdf`까지다. Studio에서 실행할 때 설정 번호와 파일 목록을 확인하고, 결과를 정답지의 7개 키와 비교한다. 게시·결제·삭제·실제 서류 업로드는 이 설계 범위에 포함하지 않는다."))
    sect = SubElement(body, q("sectPr")); pg = SubElement(sect, q("pgSz")); pg.set(q("w"), "9026"); pg.set(q("h"), "12730")
    mar = SubElement(sect, q("pgMar")); mar.set(q("top"), "720"); mar.set(q("right"), "720"); mar.set(q("bottom"), "720"); mar.set(q("left"), "720")
    return body

def main():
    document = Element(q("document"))
    document.append(build_body())
    diagram = ROOT / "submission/final/workflow_diagram.png"
    xml = tostring(document, encoding="utf-8", xml_declaration=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(TEMPLATE) as zin, ZipFile(OUT, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml": zout.writestr(item, xml)
            elif item.filename == "word/_rels/document.xml.rels":
                rels=zin.read(item.filename).decode('utf-8')
                rels=rels.replace('</Relationships>', '<Relationship Id="rIdDiagram" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/workflow_diagram.png"/></Relationships>')
                zout.writestr(item, rels.encode('utf-8'))
            elif item.filename == '[Content_Types].xml':
                ct=zin.read(item.filename).decode('utf-8')
                if 'Extension="png"' not in ct: ct=ct.replace('</Types>','<Default Extension="png" ContentType="image/png"/></Types>')
                zout.writestr(item, ct.encode('utf-8'))
            else: zout.writestr(item, zin.read(item.filename))
        zout.write(diagram, 'word/media/workflow_diagram.png')
    print(OUT)

if __name__ == "__main__": main()
