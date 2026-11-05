"""정답지 값을 공식 서식에 채워 가상 서류 이미지를 만든다. 값은 answers/에서만 읽는다.

필요: pip install pymupdf pillow
실행: python3 scripts/render_cases.py [케이스 번호 ...]
"""
import io
import json
import random
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
FONT_FILE = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
FONT = fitz.Font(fontfile=FONT_FILE)
DPI = 200
FAINT = (0.8, 0.8, 0.8)
INK = (0.05, 0.05, 0.12)

# 이번에 만드는 20건
DEFAULT_CASES = [1, 3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 19, 20, 23, 24, 25, 26, 27, 28, 29]
FORMS = {
    "6": "form06_receipt_table.pdf", "7": "form07_receipt_bracket.pdf", "8": "form08_oriental_table.pdf",
    "9": "form09_oriental_bracket.pdf", "10": "form10_pharmacy_table.pdf", "11": "form11_pharmacy_bracket.pdf",
    "12": "form12_simple_receipt.pdf", "12-2": "form12-2_payment_cert.pdf", "13": "form13_trap_ledger.pdf",
    "md-9": "form_md09_prescription.pdf", "md-5-2": "form_md05-2_diagnosis.pdf",
}
BRACKET_FORMS = {"7", "9", "11"}
# 서식 칸 이름과 정답지 행 이름이 다른 경우. (칸 이름, 같은 이름 중 몇 번째)
ROW_LABELS = {
    "투약 및 조제료 행위료": ("행위료", 0), "투약 및 조제료 약품비": ("약품비", 0),
    "주사료 행위료": ("행위료", 1), "주사료 약품비": ("약품비", 1),
    "입원료 4인실 이상": ("4인실이상", 0), "약품비": ("약품비", 0),
}
COLUMNS = ("copay", "insurer", "full_copay", "noncovered")
FAKE = {"address": "가상시 가상구 가상로 1", "business": "000-00-00000", "phone": "000-000-0000",
        "owner": "가상대표", "patient_no": "V0000000", "kind": "건강보험"}
RIGHT_PANEL = (
    ("bill_total", ("진료비총액", "약제비총액")), ("insurer_grand_total", ("공단부담총액",)),
    ("patient_total", ("환자부담총액",)), ("prepaid", ("이미납부한금액",)), ("due", ("납부할금액",)),
    ("paid_card", ("카드",)), ("paid_cash_receipt", ("현금영수증",)), ("paid_cash", ("현금",)),
    ("paid_total", ("합계",)), ("unpaid", ("납부하지않은금액",)),
)


def money(value):
    return f"{value:,}"


class Sheet:
    """서식 한 쪽. 칸 이름으로 위치를 찾아 값을 쓴다."""

    def __init__(self, page, bracket=False):
        self.page, self.bracket = page, bracket
        self.missing = []
        self.words = page.get_text("words")
        self.hlines, self.vlines = [], []
        for drawing in page.get_drawings():
            for item in drawing["items"]:
                if item[0] == "l":
                    self._line(item[1], item[2])
                elif item[0] == "re":
                    r = item[1]
                    if r.width < 2:
                        self.vlines.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                    elif r.height < 2:
                        self.hlines.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
                    else:
                        for a, b in ((r.tl, r.tr), (r.bl, r.br), (r.tl, r.bl), (r.tr, r.br)):
                            self._line(a, b)
        self.spans = self._bracket_spans() if bracket else []

    def _line(self, a, b):
        if abs(a.y - b.y) < 1:
            self.hlines.append((a.y, min(a.x, b.x), max(a.x, b.x)))
        elif abs(a.x - b.x) < 1:
            self.vlines.append((a.x, min(a.y, b.y), max(a.y, b.y)))

    def _bracket_spans(self):
        opens = sorted(self.page.search_for("["), key=lambda r: (round(r.y0), r.x0))
        closes = self.page.search_for("]")
        spans = []
        for o in opens:
            same = [c for c in closes if abs(c.y0 - o.y0) < 3 and c.x0 > o.x0]
            if same:
                spans.append(fitz.Rect(o.x1, o.y0 - 1, min(same, key=lambda c: c.x0).x0, o.y1 + 1))
        return spans

    def find(self, label, nth=0, min_x=0):
        target = label.replace(" ", "")
        lines = {}
        for w in self.words:
            lines.setdefault((w[5], w[6]), []).append(w)
        found = []
        for words in lines.values():
            for i in range(len(words)):
                joined, rect = "", None
                for w in words[i:]:
                    joined += w[4]
                    rect = fitz.Rect(w[:4]) if rect is None else rect | fitz.Rect(w[:4])
                    if target in joined and (joined == target or len(target) >= 4 or len(joined) - len(target) <= 3):
                        if rect.x0 >= min_x:
                            found.append(fitz.Rect(rect))
                        break
                    if len(joined) > len(target) + 3 and len(target) < 4:
                        break
        found.sort(key=lambda r: (round(r.y0 / 3), r.x0))
        unique = []
        for r in found:
            if not any(abs(r.y0 - u.y0) < 2 and abs(r.x1 - u.x1) < 2 for u in unique):
                unique.append(r)
        return unique[nth] if nth < len(unique) else None

    def cell_at(self, x, y):
        lefts = [v[0] for v in self.vlines if v[0] < x - 0.5 and v[1] - 1 <= y <= v[2] + 1]
        rights = [v[0] for v in self.vlines if v[0] > x + 0.5 and v[1] - 1 <= y <= v[2] + 1]
        tops = [h[0] for h in self.hlines if h[0] < y - 0.5 and h[1] - 1 <= x <= h[2] + 1]
        bottoms = [h[0] for h in self.hlines if h[0] > y + 0.5 and h[1] - 1 <= x <= h[2] + 1]
        if not (lefts and rights and tops and bottoms):
            return None
        return fitz.Rect(max(lefts), max(tops), min(rights), min(bottoms))

    def write(self, rect, text, align="right", size=8.5, color=INK):
        if text in (None, ""):
            return
        text = str(text)
        room = max(rect.width - 3, 4)
        while FONT.text_length(text, size) > room and size > 4:
            size -= 0.25
        width = FONT.text_length(text, size)
        x = rect.x1 - width - 1.5 if align == "right" else rect.x0 + 1.5 if align == "left" else (rect.x0 + rect.x1 - width) / 2
        y = (rect.y0 + rect.y1) / 2 + size * 0.36
        self.page.insert_text((x, y), text, fontname="ag", fontfile=FONT_FILE, fontsize=size, color=color)

    def erase(self, rect):
        self.page.draw_rect(rect, color=None, fill=(1, 1, 1))

    def slots_after(self, label_rect, band=4):
        y = (label_rect.y0 + label_rect.y1) / 2
        spans = [s for s in self.spans if abs((s.y0 + s.y1) / 2 - y) <= band and s.x0 > label_rect.x1 - 2]
        if not spans:
            return []
        # 같은 줄 괄호만 남긴다. 위아래 줄의 괄호에 쓰지 않기 위해서다.
        nearest = min(abs((s.y0 + s.y1) / 2 - y) for s in spans)
        return sorted((s for s in spans if abs((s.y0 + s.y1) / 2 - y) <= nearest + 2), key=lambda s: s.x0)

    def value_right(self, label_rect, text, style=None):
        """칸 이름 오른쪽 값 칸에 쓴다."""
        style = style or {}
        y = (label_rect.y0 + label_rect.y1) / 2
        if self.bracket:
            spans = [s for s in self.spans if abs((s.y0 + s.y1) / 2 - y) <= 14 and s.x0 > label_rect.x1 - 2]
            if not spans:
                return False
            # 두 줄짜리 칸 이름이 다음 칸의 괄호를 잡지 않도록 가로 거리도 함께 본다.
            near = min(spans, key=lambda s: abs((s.y0 + s.y1) / 2 - y) + (s.x0 - label_rect.x1) * 0.1)
            self.write(near, text, **style)
            return True
        cell = self.cell_at((label_rect.x0 + label_rect.x1) / 2, y)
        if cell is None:
            return False
        target = self.cell_at(cell.x1 + 3, y)
        if target is None:
            return False
        self.write(target, text, **style)
        return True

    def value_below(self, label, text, nth=0, align="center"):
        """표 서식은 칸 이름 아래, 괄호 서식은 칸 이름 옆에 쓴다."""
        rect = self.find(label, nth)
        if rect is None:
            self.missing.append(label)
            return
        if self.bracket:
            slots = self.slots_after(rect)
            if slots:
                self.write(slots[0], text)
            else:
                self.missing.append(label)
            return
        cell = self.cell_at((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        below = self.cell_at((rect.x0 + rect.x1) / 2, cell.y1 + 3) if cell else None
        if below is None:
            self.missing.append(label)
            return
        self.write(below, text, align=align)

    def tick(self, label):
        rect = self.find(label)
        if rect is None:
            self.missing.append(label)
            return
        self.page.insert_text((rect.x0 - 6.5, rect.y1 - 3), "V", fontname="ag", fontfile=FONT_FILE, fontsize=8, color=INK)

    def period(self, start, end):
        """'. . .부터 . . .까지' 칸을 날짜로 바꿔 쓴다."""
        fr, to = self.find("부터"), self.find("까지")
        if fr is None or to is None:
            self.missing.append("진료기간")
            return
        rect = fitz.Rect(fr.x0 - 44, min(fr.y0, to.y0) - 0.5, to.x1 + 0.5, max(fr.y1, to.y1) + 0.5)
        self.erase(rect)
        self.write(rect, f"{start} 부터 {end} 까지" if end else f"{start} 부터", align="center", size=7.5)

    def issue_date(self, day):
        if not day:
            return
        y_, m_, d_ = day.split("-")
        years = [w for w in self.words if w[4] == "년"]
        if not years:
            self.missing.append("발행일")
            return
        year = fitz.Rect(max(years, key=lambda w: w[1])[:4])
        same = [w for w in self.words if abs(w[1] - year.y0) < 3]
        for word, text in (("년", y_), ("월", m_), ("일", d_)):
            target = next((w for w in same if w[4] == word), None)
            if target:
                self.write(fitz.Rect(target[0] - 34, target[1], target[0] - 1, target[3]), text)


def as_doc(answer, doc):
    values = {f["key"]: f["value"] for f in answer["fields"] if f["file_name"] == doc["file_name"]}
    return values


def fill_receipt(sheet, form, values, department_day, faint_keys):
    """진료비·약제비 영수증."""
    day = values.get("visit_start") or values.get("issue_date")
    is_pharmacy = form in ("10", "11")
    if is_pharmacy:
        number = sheet.find("영수증번호")
        if form == "10" and number is not None:
            # 제10호서식은 번호 칸이 칸 이름 오른쪽에 있다.
            sheet.value_right(number, values.get("receipt_no"), {"align": "left"})
        else:
            sheet.value_below("영수증번호", values.get("receipt_no"))
        sheet.value_below("환자 성명", values.get("patient_name"))
        sheet.value_below("조제일", day)
        sheet.value_below("투약일수", "3")
    else:
        sheet.value_below("환자등록번호", FAKE["patient_no"])
        sheet.value_below("환자 성명" if form != "9" else "환자성명", values.get("patient_name"))
        sheet.value_below("진료 과목" if form != "12" else "환자등록번호", values.get("department") if form != "12" else None)
        if form != "12":
            sheet.value_below("환자 구분", FAKE["kind"])
            sheet.value_below("영수증번호", values.get("receipt_no"))
            if values.get("visit_start"):
                sheet.period(values["visit_start"], values.get("visit_end"))
            sheet.tick("외래" if values.get("visit_type") != "입원" else "입원")
            if values.get("visit_type") == "입원":
                sheet.tick("퇴원")
        else:
            sheet.value_below("진료일", day)

    # 합계 행의 ①②③④로 열 위치를 잡는다.
    totals = [r for r in (sheet.find("합계", i) for i in range(5)) if r is not None]
    total = min(totals, key=lambda r: r.x0)
    marks = {}
    for mark, column in zip("①②③④", COLUMNS):
        marks[column] = min(sheet.page.search_for(mark), key=lambda r: abs(r.y0 - total.y0))
    total_y = (marks["copay"].y0 + marks["copay"].y1) / 2

    def row_cell(y, column):
        if sheet.bracket:
            return None
        mark = marks[column]
        return sheet.cell_at(mark.x0 + 10, y)

    for key, value in values.items():
        if not key.startswith("row:") or value in (0, None):
            continue
        _, name, column = key.split(":")
        label, nth = ROW_LABELS.get(name, (name, 0))
        rect = sheet.find(label, nth) or sheet.find(name.split()[0])
        if rect is None or rect.y0 > total_y:
            sheet.missing.append(name)
            continue
        if sheet.bracket:
            slots = sheet.slots_after(rect)
            if len(slots) > COLUMNS.index(column):
                sheet.write(slots[COLUMNS.index(column)], money(value))
            else:
                sheet.missing.append(name)
        else:
            cell = row_cell((rect.y0 + rect.y1) / 2, column)
            if cell is None:
                sheet.missing.append(name)
            else:
                sheet.write(cell, money(value))

    for column, key in zip(COLUMNS, ("copay_total", "insurer_total", "full_copay_total", "noncovered_total")):
        value = values.get(key)
        if value is None:
            continue
        style = {"color": FAINT} if key in faint_keys else {}
        mark = marks[column]
        if sheet.bracket:
            slots = [s for s in sheet.slots_after(fitz.Rect(mark.x0, mark.y0, mark.x1, mark.y1)) if s.x0 >= mark.x0]
            if slots:
                sheet.write(slots[0], money(value), **style)
        else:
            cell = sheet.cell_at(mark.x1 + 5, total_y)
            if cell is not None:
                sheet.write(fitz.Rect(mark.x1, cell.y0, cell.x1, cell.y1), money(value), **style)

    if values.get("cap_excess"):
        mark = sorted(sheet.page.search_for("⑤"), key=lambda r: -r.y0)[0]
        if sheet.bracket:
            slots = sheet.slots_after(mark)
            if slots:
                sheet.write(slots[0], money(values["cap_excess"]))
        else:
            cell = sheet.cell_at(mark.x1 + 5, (mark.y0 + mark.y1) / 2)
            if cell is not None:
                sheet.write(fitz.Rect(mark.x1, cell.y0, cell.x1, cell.y1), money(values["cap_excess"]))

    # 오른쪽 금액 칸. 합계 행의 '합계'와 겹치지 않게 x로 나눈다.
    card_x = (sheet.find("카드") or fitz.Rect(250, 0, 260, 1)).x0 - 5
    for key, labels in RIGHT_PANEL:
        value = values.get(key)
        if value in (None, 0) or (key == "due" and form in ("10", "11", "12")):
            continue
        rect = None
        for label in labels:
            rect = sheet.find(label, 0, min_x=card_x if key.startswith("paid") else 0)
            if rect is not None:
                break
        if rect is None or not sheet.value_right(rect, money(value)):
            sheet.missing.append(key)

    if not is_pharmacy:
        sheet.value_right(sheet.find("사업자등록번호") or fitz.Rect(), FAKE["business"], {"align": "left"}) if sheet.find("사업자등록번호") else None
    provider = sheet.find("상호", 0) or sheet.find("상  호", 0) or sheet.find("명칭", 0)
    if provider is None:
        sheet.missing.append("상호")
    elif sheet.bracket and not sheet.slots_after(provider):
        # 제7호서식의 상호 칸에는 괄호가 없다.
        sheet.write(fitz.Rect(provider.x1 + 8, provider.y0 - 2, provider.x1 + 150, provider.y1 + 2), values.get("provider_name"), align="left")
    else:
        sheet.value_right(provider, values.get("provider_name"), {"align": "left"})
    address = sheet.find("사업장 소재지")
    if address is not None:
        sheet.value_right(address, FAKE["address"], {"align": "left"})
    phone = sheet.find("전화번호", 0, min_x=250)
    if phone is not None:
        sheet.value_right(phone, FAKE["phone"], {"align": "left"})
    sheet.issue_date(department_day)


def fill_payment_cert(sheet, values):
    name = sheet.find("환자 성명")
    if name is not None:
        sheet.value_right(name, values.get("patient_name"), {"align": "center"})
    provider = sheet.find("상호") or sheet.find("명칭")
    if provider is not None:
        sheet.value_right(provider, values.get("provider_name"), {"align": "left"})
    # 납입 내역 첫 줄. ①②③④는 칸 머리글의 번호로 찾고, 나머지는 칸 이름으로 찾는다.
    formula = sheet.find("(①+②+③+④)") or sheet.find("총액")
    headers = {
        "date": sheet.find("조제일자"), "visit_type": sheet.find("구분"), "total": sheet.find("총액"),
        "patient_total": sheet.find("총액", 1), "card": sheet.find("카드"),
    }
    for mark, key in zip("①②③④", ("insurer", "copay", "full_copay", "noncovered")):
        # 총액 칸의 식에도 같은 번호가 있어 그 칸들은 뺀다.
        limit = headers["patient_total"].x0 - 20 if headers["patient_total"] else 10000
        rects = [r for r in sheet.page.search_for(mark) if (formula is None or abs(r.y0 - formula.y0) > 3) and r.x0 < limit]
        headers[key] = rects[0] if rects else None
    bottom = max(r.y1 for r in headers.values() if r is not None)
    row_y = min(h[0] for h in sheet.hlines if h[0] > bottom + 2) + 30
    for key, rect in headers.items():
        if rect is None:
            sheet.missing.append(key)
            continue
        cell = sheet.cell_at((rect.x0 + rect.x1) / 2, row_y)
        value = values.get(f"line:0:{key}")
        if cell is None:
            sheet.missing.append(key)
        elif key in ("date", "visit_type"):
            sheet.write(cell, value, align="center", size=7)
        else:
            sheet.write(cell, money(value or 0))


def fill_prescription(sheet, values):
    sheet.tick("건강보험")
    doctor = sheet.find("의료인의")
    if doctor is not None and values.get("disease_code"):
        # 처방전 서식은 점선이 많아 칸 선 대신 옆 칸 위치로 잡는다.
        sheet.write(fitz.Rect(100, doctor.y0 - 8, doctor.x0 - 6, doctor.y1 + 22), values["disease_code"], align="center", size=10)
    name = sheet.find("성명", 0)
    if name is not None:
        sheet.value_right(name, values.get("patient_name"), {"align": "center"})
    place = sheet.find("칭", 0, min_x=300)
    if place is None:
        sheet.missing.append("명칭")
    else:
        sheet.write(fitz.Rect(place.x1 + 14, place.y0 - 2, 555, place.y1 + 2), values.get("provider_name"), align="left", size=9)
    period = sheet.find("발급 연월일 및 번호")
    if period is not None:
        cell = sheet.cell_at(period.x1 + 40, (period.y0 + period.y1) / 2)
        if cell is not None:
            sheet.erase(fitz.Rect(cell.x0 + 1, cell.y0 + 1, cell.x1 - 1, cell.y1 - 1))
            sheet.write(cell, f"{values['issue_date']} - 제 {values.get('issue_no', '')} 호", align="center", size=7.5)
    rects = sheet.page.search_for("일간")
    if rects:
        r = rects[0]
        sheet.write(fitz.Rect(r.x0 - 24, r.y0, r.x0 - 2, r.y1), values.get("valid_days"), align="center", size=8)
    head = sheet.find("처방 의약품의")
    if head is None:
        sheet.missing.append("처방 의약품")
        return
    # 첫 약 줄에 값을 쓴다. 칸마다 머리글의 가로 위치로 찾는다.
    first_y = min(h[0] for h in sheet.hlines if h[0] > head.y1 + 12) + 6
    sheet.write(fitz.Rect(head.x0 - 12, first_y - 5, head.x1 + 45, first_y + 7), f"{values.get('drug:0:name', '')} {values.get('drug:0:code', '')}", align="left", size=8)
    for label, key in (("약량", "dose"), ("투여횟수", "daily"), ("투약일수", "days")):
        rect = sheet.find(label)
        if rect is not None:
            sheet.write(fitz.Rect(rect.x0 - 8, first_y - 5, rect.x1 + 8, first_y + 7), values.get(f"drug:0:{key}"), align="center", size=8)


def fill_diagnosis(sheet, values):
    name = sheet.find("환자의 성명")
    if name is None:
        sheet.missing.append("환자의 성명")
    else:
        sheet.write(fitz.Rect(name.x1 + 30, name.y0 - 2, name.x1 + 200, name.y1 + 2), values.get("patient_name"), align="left", size=10)
    main = sheet.find("(주 질병")
    if main is not None:
        sheet.write(fitz.Rect(main.x1 + 8, main.y0 - 2, main.x1 + 150, main.y1 + 2), values.get("disease_name"), align="left", size=9)
    code = sheet.find("질병분류기호")
    if code is not None:
        sheet.write(fitz.Rect(code.x0 - 10, code.y1 + 3, code.x1 + 10, code.y1 + 20), values.get("disease_code"), align="center", size=10)
    if values.get("diagnosis_type") == "최종 진단":
        sheet.tick("최종 진단")
    day = sheet.find("진단 연월일")
    if day is not None:
        rect = fitz.Rect(day.x1 + 8, day.y0 - 1, day.x1 + 115, day.y1 + 1)
        sheet.erase(rect)
        sheet.write(rect, values.get("diagnosis_date"), align="center", size=9)
    start, end = sheet.find("입원일"), sheet.find("퇴원일")
    if start is not None and end is not None:
        rect = fitz.Rect(start.x1 + 4, start.y0 - 1, end.x0 - 8, start.y1 + 1)
        sheet.erase(rect)
        sheet.write(rect, f"{values.get('admission_date')} 부터", align="left", size=8)
        rect = fitz.Rect(end.x1 + 4, end.y0 - 1, end.x1 + 95, end.y1 + 1)
        sheet.erase(rect)
        sheet.write(rect, values.get("discharge_date"), align="left", size=8)
    place = sheet.find("의료기관 명칭")
    if place is None:
        sheet.missing.append("의료기관 명칭")
    else:
        sheet.write(fitz.Rect(place.x1 + 6, place.y0 - 2, place.x1 + 220, place.y1 + 2), values.get("provider_name"), align="left", size=10)
    sheet.issue_date(values.get("issue_date"))


def text_page(title, rows, note=None):
    """공통 서식을 찾지 못한 확인서와 카드 전표."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=420 if len(rows) <= 8 else 841)
    sheet = Sheet(page)
    sheet.write(fitz.Rect(40, 30, 555, 70), title, align="center", size=18)
    y = 90
    for label, value in rows:
        page.draw_rect(fitz.Rect(60, y, 200, y + 28), color=(0, 0, 0), width=0.6)
        page.draw_rect(fitz.Rect(200, y, 535, y + 28), color=(0, 0, 0), width=0.6)
        sheet.write(fitz.Rect(60, y, 200, y + 28), label, align="center", size=10)
        sheet.write(fitz.Rect(205, y, 530, y + 28), value, align="left", size=10)
        y += 28
    if note:
        sheet.write(fitz.Rect(60, y + 14, 535, y + 40), note, align="center", size=9)
    return doc


def itemized_page(values):
    """진료비 세부산정내역 서식의 칸을 그대로 그린다. 원본이 HWP라 직접 그린다."""
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    sheet = Sheet(page)
    sheet.write(fitz.Rect(30, 18, 812, 50), "진료비 세부산정내역", align="center", size=16)
    sheet.write(fitz.Rect(30, 52, 400, 70), f"환자 성명: {values.get('patient_name')}   등록번호: {FAKE['patient_no']}", align="left", size=9)
    sheet.write(fitz.Rect(400, 52, 812, 70), f"요양기관: {values.get('provider_name')}   진료기간: {values.get('visit_start')} ~ {values.get('visit_end')}", align="right", size=9)
    headers = ["항목", "일자", "코드", "명칭", "횟수", "일수", "총액", "본인부담금", "공단부담금", "전액본인부담", "비급여"]
    widths = [90, 62, 48, 150, 30, 30, 66, 66, 66, 70, 70]
    x0, y = 28, 76

    def row(cells, height=22, align=None):
        nonlocal y
        x = x0
        for i, (cell, width) in enumerate(zip(cells, widths)):
            rect = fitz.Rect(x, y, x + width, y + height)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            sheet.write(rect, cell, align=(align or ("left" if i < 4 else "right")), size=8)
            x += width
        y += height

    row(headers, align="center")
    count = 1 + max([int(k.split(":")[1]) for k in values if k.startswith("line:")] + [-1])
    for i in range(count):
        get = lambda c: values.get(f"line:{i}:{c}")
        row([get("item"), get("date"), get("code"), get("name"), get("count"), get("days")] + [money(get(c) or 0) for c in ("total", "copay", "insurer", "full_copay", "noncovered")])
    for label, part in (("계", "subtotal"), ("끝수처리 조정금액", "adjustment"), ("합계", "grand_total")):
        row([label, "", "", "", "", ""] + [money(values.get(f"{part}.{c}", 0)) for c in ("total", "copay", "insurer", "full_copay", "noncovered")])
    return doc


def capture(pixmap, how, seed, crop_right=None):
    """스캔이나 촬영처럼 보이게 한다. 실제 촬영과 같지는 않다."""
    rng = random.Random(seed)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    how = how or ""
    if crop_right:
        image = image.crop((0, 0, int(image.width * crop_right), image.height))
    if "구긴" in how:
        w, h = image.size
        shade = Image.new("L", (w // 16, h // 16), 255)
        shade.putdata([rng.randint(225, 255) for _ in range(shade.width * shade.height)])
        shade = shade.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(14))
        image = ImageChops.multiply(image, Image.merge("RGB", (shade, shade, shade)))
    if "그림자" in how:
        w, h = image.size
        shade = Image.new("L", (w, h), 255)
        shade.paste(150, (int(w * 0.45), int(h * 0.1), w, int(h * 0.5)))
        shade = shade.filter(ImageFilter.GaussianBlur(40))
        image = ImageChops.multiply(image, Image.merge("RGB", (shade, shade, shade)))
    angle = 15 if "15도" in how else rng.uniform(-0.6, 0.6)
    if "구긴" in how:
        angle = rng.uniform(-2.0, 2.0)
    image = image.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(245, 245, 240))
    image = image.filter(ImageFilter.GaussianBlur(0.45))
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.96, 1.0))
    return image


def render_doc(answer, doc, faint_keys, seed):
    values = as_doc(answer, doc)
    kind, form = doc["type"], doc.get("form_no")
    missing = []
    if kind == "itemized_bill":
        pdf = itemized_page(values)
    elif kind == "visit_cert":
        pdf = text_page("통원확인서" if answer["claim_type"] == "outpatient" else "입퇴원확인서", [
            ("환자 성명", values.get("patient_name")), ("진단명", values.get("disease_name")),
            ("질병분류기호", values.get("disease_code")),
            ("진료 기간", f"{values.get('visit_start')} ~ {values.get('visit_end')}"),
            ("요양기관명", values.get("provider_name")), ("발행일", values.get("visit_end")),
        ], "위와 같이 진료받았음을 확인합니다.")
    elif kind == "other" and form != "13":
        pdf = text_page("신용카드 매출전표", [
            ("가맹점명", "가상의원"), ("사업자번호", FAKE["business"]), ("거래일시", "2026-11-04 10:30"),
            ("카드번호", "0000-00**-****-0000"), ("승인번호", "00000000"), ("결제 금액", "24,000원"),
        ])
    else:
        pdf = fitz.open(ROOT / "forms" / FORMS[form])
        sheet = Sheet(pdf[0], bracket=form in BRACKET_FORMS)
        if kind in ("receipt", "simple_receipt", "pharmacy_receipt"):
            day = values.get("visit_end") or values.get("issue_date")
            if doc.get("reissued"):
                day = doc["reissued"]
            fill_receipt(sheet, form, values, day, faint_keys)
        elif kind == "payment_cert":
            fill_payment_cert(sheet, values)
        elif kind == "prescription":
            fill_prescription(sheet, values)
        elif kind == "diagnosis":
            fill_diagnosis(sheet, values)
        missing = sheet.missing
    pixmap = pdf[0].get_pixmap(dpi=DPI)
    crop = 0.62 if "CROPPED" in doc.get("flags", []) else None
    return capture(pixmap, answer.get("capture"), seed, crop), missing


def faint_keys_for(answer):
    return {"copay_total"} if "연하게" in (answer.get("capture") or "") else set()


def main():
    numbers = [int(a) for a in sys.argv[1:]] or DEFAULT_CASES
    problems = 0
    for number in numbers:
        case = f"case_{number:02d}"
        answer = json.loads((ROOT / "answers" / f"{case}.json").read_text(encoding="utf-8"))
        folder = ROOT / "cases" / case
        folder.mkdir(parents=True, exist_ok=True)
        for index, doc in enumerate(answer["documents"]):
            if number == 27 and index == 1:
                doc["reissued"] = "2026-11-06"
            image, missing = render_doc(answer, doc, faint_keys_for(answer), f"{case}{index}")
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=82, optimize=True)
            (folder / f"{doc['file_name']}.jpg").write_bytes(buffer.getvalue())
            if missing:
                problems += 1
                print(case, doc["file_name"], "못 찾은 칸:", missing)
    print("완료", len(numbers), "건, 칸 문제", problems)


if __name__ == "__main__":
    main()
