"""최종 제출 발표 자료 PDF를 만든다. 한글 글꼴을 PDF 안에 넣어 어디서 열어도 글자가 보이게 한다.

필요: pip install pymupdf
실행: python3 scripts/make_slides.py

숫자는 submission/final/의 채점 결과(score_studio_16.json, score_holdout_16.json)에서 읽는다.
"""
import json
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "submission" / "final"
OUT = FINAL / "컴학감동_최종제출_발표자료.pdf"
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
W, H = 960, 540
INK, MUTED, ACCENT, SOFT, LINE = (0.07, 0.09, 0.15), (0.38, 0.4, 0.46), (0.31, 0.27, 0.9), (0.93, 0.94, 1.0), (0.85, 0.86, 0.9)
KEYS = ["patient_name", "provider_name", "decision", "cause", "missing_documents", "mismatches"]


def score(name):
    path = FINAL / name
    if not path.exists():
        return None
    by_key = json.loads(path.read_text(encoding="utf-8"))["by_key"]
    rows = [(k, by_key[k]["match"], by_key[k]["total"]) for k in KEYS]
    return rows, sum(r[1] for r in rows), sum(r[2] for r in rows)


class Deck:
    def __init__(self):
        self.doc = fitz.open()
        self.number = 0

    def page(self, title, kicker=None):
        self.number += 1
        page = self.doc.new_page(width=W, height=H)
        page.insert_font(fontname="kr", fontfile=FONT)
        page.draw_rect(fitz.Rect(0, 0, W, 6), color=None, fill=ACCENT)
        if kicker:
            self.text(page, 48, 30, kicker, 13, ACCENT)
        self.text(page, 48, 48 if kicker else 36, title, 28, INK)
        self.text(page, 48, H - 30, "컴학감동 · 최종 제출 · 설정 #16", 10, MUTED)
        self.text(page, W - 70, H - 30, f"{self.number:02d}", 10, MUTED)
        return page

    def text(self, page, x, y, value, size=16, color=INK):
        page.insert_text((x, y + size), value, fontname="kr", fontsize=size, color=color)

    def box(self, page, rect, value, size=16, color=INK, fill=None, border=None):
        rect = fitz.Rect(rect)
        if fill or border:
            page.draw_rect(rect, color=border, fill=fill, width=1, radius=0.06)
            rect = rect + (14, 12, -14, -10)
        page.insert_textbox(rect, value, fontname="kr", fontsize=size, color=color, lineheight=1.35)

    def bullets(self, page, x, y, items, size=18, width=860, gap=14):
        for item in items:
            page.draw_circle(fitz.Point(x + 5, y + size * 0.65), 3.5, color=None, fill=ACCENT)
            rect = fitz.Rect(x + 20, y, x + width, y + 200)
            used = page.insert_textbox(rect, item, fontname="kr", fontsize=size, color=INK, lineheight=1.3)
            lines = max(1, round((200 - used) / (size * 1.3)))
            y += lines * size * 1.3 + gap
        return y

    def table(self, page, x, y, widths, rows, size=14, height=28):
        for r, row in enumerate(rows):
            cx = x
            for c, value in enumerate(row):
                rect = fitz.Rect(cx, y, cx + widths[c], y + height)
                page.draw_rect(rect, color=LINE, fill=SOFT if r == 0 else None, width=0.6)
                page.insert_textbox(rect + (8, 6, -6, 0), str(value), fontname="kr", fontsize=size, color=INK)
                cx += widths[c]
            y += height
        return y

    def save(self):
        self.doc.set_metadata({"title": "컴학감동 최종 제출 발표자료", "author": "컴학감동"})
        self.doc.save(OUT, deflate=True, garbage=3)


def main():
    final, holdout = score("score_studio_16.json"), score("score_holdout_16.json")
    deck = Deck()

    p = deck.page("실손보험 청구 서류 1차 검증 워크플로우", "컴학감동 · 최종 제출")
    deck.box(p, (48, 130, 900, 260), "보상 담당자가 받은 청구 서류 묶음을 읽고, 영수증 금액을 검산하고, 서류 누락·불일치·중복을 찾아 심사 진행 / 보완 요청 / 검토 필요 중 하나로 1차 분류합니다.", 20)
    deck.box(p, (48, 300, 420, 420), "Upstage Studio 설정 #16\nParse → Classify → Extract → 판정", 17, fill=SOFT, border=LINE)
    if final:
        deck.box(p, (450, 300, 900, 420), f"최종 데이터셋 32개 × 2회\n키 일치 {final[1]}/{final[2]}", 17, fill=SOFT, border=LINE)

    p = deck.page("문제와 사용자")
    deck.bullets(p, 48, 110, [
        "실손 청구 서류는 영수증·처방전·세부내역서·확인서가 한 파일에 섞여 들어온다.",
        "담당자는 금액 검산, 같은 영수증 중복, 서류 간 금액·이름 차이, 금액·진료과별 필요 서류를 손으로 확인한다.",
        "대상 사용자: 서류를 접수하는 보상 담당자. 결과는 판정 + 원인 + 근거 + 보완 요청 문구로 받는다.",
        "범위 밖: 보험금 지급 여부, 의학적 판단, 보험사기 판단.",
    ], size=20, gap=18)

    p = deck.page("워크플로우 (설정 #16)")
    p.insert_image(fitz.Rect(40, 95, 920, 375), filename=str(FINAL / "workflow_diagram.png"), keep_proportion=True)
    deck.bullets(p, 48, 390, [
        "판정_근거: 규칙대로 판단한다. 문서를 참조해 인용 표시가 붙는다.",
        "청구_판정: 7개 키를 같은 값으로 옮기며 인용 표시만 지우고, 판정별로 분기한다.",
        "blank(빈 페이지)는 어디에도 연결하지 않고, 기타 문서는 판정 근거로 세지 않는다.",
    ], size=15, gap=6)

    p = deck.page("판정 규칙 순서")
    deck.table(p, 48, 105, [150, 420, 294], [
        ["순서", "규칙", "이 순서인 이유"],
        ["사전", "영수증이 없으면 보완 요청 / 서류 누락", "없는 것과 못 읽은 것을 구분"],
        ["1 읽기 점검", "①+②+③+④ = 총액, ①-⑤+③+④ = 환자부담 검산", "잘못 읽은 값으로 비교하지 않게"],
        ["2 중복", "기관 + 영수증 번호가 같으면 중복 제출", "같은 금액을 두 번 세지 않게"],
        ["3 서류 비교", "세부내역서 합계·이름·기관을 영수증과 비교", "검산을 통과한 값끼리만 비교"],
        ["4 필요 서류", "입원 → 진료과 예외 → 10만 원 초과 → 3만 원 초과", "처음 맞는 줄 하나만 적용"],
        ["5 최종", "걸린 단계가 없으면 심사 진행", "목록 두 개는 반드시 []"],
    ], size=14, height=50)

    p = deck.page("신뢰성 설계: 왜 흔들리지 않게 만들었나")
    deck.box(p, (48, 100, 330, 420), "검산을 가장 먼저\n\nA와 B를 두 수씩 더해 적게 한다. 하나라도 다르면 바로 검토 필요 / 읽기 오류로 끝내고 뒤 단계로 원인을 바꾸지 않는다.\n\n효과: 계산 흔들림이 사라져 #8에서 85회 모두 일치", 18, fill=SOFT, border=LINE)
    deck.box(p, (345, 100, 625, 420), "판정과 정리를 분리\n\n프롬프트로 금지해도 인용 표시가 24회 중 9회 남았다. 판정_근거와 청구_판정(정리)으로 나눠, 채점하는 7개 키에 인용 표시가 붙지 않게 했다.\n\n효과: 청구_판정 인용 표시 76회 중 0회", 18, fill=SOFT, border=LINE)
    deck.box(p, (640, 100, 920, 420), "실패를 막는 분류\n\n빈 페이지는 blank로 보내 청구 전체가 실패하지 않게 하고, 카드 전표 같은 기타 문서는 판정 근거로 쓰지 않는다.\n\n효과: 빈 페이지가 섞인 청구도 판정이 나옴", 18, fill=SOFT, border=LINE)

    p = deck.page("개선 과정")
    history = [("#4", 7, 13, "통원 규칙 충돌"), ("#5", 38, 39, "판정 순서 고정"), ("#8", 85, 85, "두 수씩 검산"),
               ("#10", 38, 38, "blank 추가")]
    if final:
        history.append(("#16", final[1], final[2], "판정·정리 분리"))
    base, top, bar = 380, 120, 100
    for i, (name, ok, total, note) in enumerate(history):
        x = 70 + i * 140
        h = (base - top) * ok / total
        p.draw_rect(fitz.Rect(x, base - h, x + bar, base), color=None, fill=ACCENT if i == len(history) - 1 else (0.7, 0.72, 0.95))
        deck.text(p, x + 8, base - h - 24, f"{ok}/{total}", 14)
        deck.text(p, x + 30, base + 8, name, 15)
        deck.box(p, (x - 10, base + 30, x + bar + 20, base + 70), note, 11, MUTED)
    deck.text(p, 48, 470, "설정별 일치 건수. #4~#10은 그때 시험 파일의 판정 4개 키 기준 실행 횟수, #16은 최종 데이터셋 32개 × 2회의 6개 키 기준", 12, MUTED)

    p = deck.page("데이터셋")
    deck.table(p, 48, 105, [260, 160], [["구분", "건수"], ["전체 세트", "32개"], ["문서", "63건"], ["심사 진행", "20"], ["보완 요청", "8"], ["검토 필요", "4"]], size=15, height=40)
    deck.bullets(p, 500, 110, [
        "① 단순 ② 양식 다양성 ③ 문서 결합 ④ 저품질 ⑤ 예외·함정 모두 포함",
        "cause 5종(없음, 서류 누락, 서류 불일치, 중복 제출, 읽기 오류) 모두 포함",
        "④ 저품질: 흐린 칸, 구김, 기울임, 그림자, 저해상도",
        "공식 서식에 팀이 만든 가상 값. 실제 환자 정보 없음",
    ], size=15, width=420)

    p = deck.page("실행 정확도")
    y = 100
    if final:
        y = deck.table(p, 48, y, [240, 200], [["키 (최종 데이터셋 32개 × 2회)", "일치"]] + [[k, f"{m}/{t}"] for k, m, t in final[0]] + [["전체", f"{final[1]}/{final[2]}"]], size=14, height=34)
    if holdout:
        deck.table(p, 510, 100, [240, 160], [["키 (홀드아웃 6개 × 2회)", "일치"]] + [[k, f"{m}/{t}"] for k, m, t in holdout[0]] + [["전체", f"{holdout[1]}/{holdout[2]}"]], size=14, height=34)
        deck.box(p, (510, 420, 920, 500), "홀드아웃: 규칙을 고칠 때 보지 않은 새 가상 영수증 3장과 그 회전·저해상도 변형", 12, MUTED)
    deck.box(p, (48, 420, 480, 500), "청구_판정 content를 정답지와 키별로 비교(scripts/score_studio.py). reason은 문장이 달라도 되는 값이라 제외", 12, MUTED)

    p = deck.page("출력 예시 (보완 요청)")
    example = (ROOT / "outputs" / "studio_run16" / "컴학감동_최종제출_set16.txt")
    content = example.read_text(encoding="utf-8").strip() if example.exists() else ""
    deck.box(p, (48, 95, 600, 495), content, 12.5, fill=SOFT, border=LINE)
    deck.box(p, (620, 95, 920, 480), "청구_판정 원문(set16)\n\n• 영수증 금액을 두 수씩 검산\n• 환자부담 54,200원 > 3만 원\n• 처방전·증빙 없음\n→ 보완 요청 / 서류 누락 / [\"처방전\"]\n\n뒤이어 보완_요청_문구 노드가 고객에게 보낼 안내문을 쓴다.\n\n\"다시 보내 주실 서류: 처방전\"", 16)

    p = deck.page("예외 처리와 한계")
    deck.table(p, 48, 100, [190, 674], [
        ["처리함", "빈 페이지(blank), 검산 불일치(읽기 오류), 기타 문서만 제출, 진료과 예외, 병원·약국 기관 차이, 인용 표시"],
        ["한계", "총액 칸이 빈 영수증은 추출이 계산식대로 값을 채워 걸러지지 않음(데이터셋에서 제외)"],
        ["한계", "글자를 거의 읽을 수 없는 흐린 문서는 OCR이 글자를 못 찾아 판정이 나오지 않음(데이터셋에서 제외)"],
        ["한계", "검산을 코드가 아닌 프롬프트로 하므로 계산 실수 가능성이 남음(두 수씩 덧셈으로 줄임)"],
        ["다음 단계", "실제 촬영 사진 추가, 청구서·약관 대조, 담당자 화면에서 보완 요청 문구 바로 발송"],
    ], size=14, height=62)

    deck.save()
    print(OUT, deck.number, "pages")


if __name__ == "__main__":
    main()
