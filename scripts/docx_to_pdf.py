"""make_design_doc.py가 만든 설계서 docx를 PDF로 옮긴다. Word 없이 한글 글꼴을 넣어 만든다.

필요: pip install pymupdf
실행: python3 scripts/docx_to_pdf.py
"""
import html
import io
from pathlib import Path
from xml.etree.ElementTree import fromstring
from zipfile import ZipFile

import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "submission" / "final" / "컴학감동_최종제출_설계서.docx"
OUT = SRC.with_suffix(".pdf")
FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
CSS = """
@font-face { font-family: kr; src: url(AppleGothic.ttf); }
* { font-family: kr; }
body { font-size: 9.5pt; line-height: 1.45; color: #111827; }
h1 { font-size: 20pt; text-align: center; margin: 0 0 4pt 0; }
h2 { font-size: 12.5pt; color: #312e81; margin: 12pt 0 4pt 0; }
p.sub { text-align: center; color: #4b5563; margin: 0 0 10pt 0; }
p { margin: 3pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 6pt 0; }
td { border: 0.5pt solid #c7c9d1; padding: 3pt 4pt; vertical-align: top; font-size: 8.5pt; }
tr.head td { background-color: #eef2ff; font-weight: bold; }
td.key { background-color: #f5f6fb; }
img { width: 100%; }
"""


def text_of(node):
    return "".join(t.text or "" for t in node.iter(W + "t"))


def to_html(document):
    body = document.find(W + "body")
    out, seen_title = [], False
    for node in body:
        if node.tag == W + "p":
            if node.find(".//" + A_BLIP) is not None:
                out.append('<p><img src="workflow_diagram.png"/></p>')
                continue
            value = html.escape(text_of(node))
            if not value:
                continue
            style = node.find(f"{W}pPr/{W}pStyle")
            name = style.get(W + "val") if style is not None else ""
            if name == "Title":
                out.append(f"<h1>{value}</h1>"); seen_title = True
            elif name == "Heading1" and seen_title and not value.startswith("-"):
                out.append(f"<h2>{value}</h2>")
            elif name == "Heading1":
                out.append(f'<p class="sub">{value}</p>')
            else:
                out.append(f"<p>{value}</p>")
        elif node.tag == W + "tbl":
            rows = []
            for r, tr in enumerate(node.findall(W + "tr")):
                key, head = ' class="key"', ' class="head"'
                cells = "".join(f"<td{key if c == 0 and r else ''}>{html.escape(text_of(tc))}</td>"
                                for c, tc in enumerate(tr.findall(W + "tc")))
                rows.append(f"<tr{head if r == 0 else ''}>{cells}</tr>")
            out.append("<table>" + "".join(rows) + "</table>")
    return out


def main():
    with ZipFile(SRC) as z:
        document = fromstring(z.read("word/document.xml"))
    archive = fitz.Archive()
    archive.add(Path(FONT).read_bytes(), "AppleGothic.ttf")
    archive.add((ROOT / "submission" / "final" / "workflow_diagram.png").read_bytes(), "workflow_diagram.png")
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    page_rect = fitz.paper_rect("a4")
    area = page_rect + (42, 42, -42, -42)
    device, top = writer.begin_page(page_rect), area.y0
    for block in to_html(document):
        story = fitz.Story(html="<body>" + block + "</body>", user_css=CSS, archive=archive)
        while True:
            rect = fitz.Rect(area.x0, top, area.x1, area.y1)
            more, filled = story.place(rect)
            if more and top > area.y0 + 1 and not block.startswith("<table"):
                writer.end_page(); device, top = writer.begin_page(page_rect), area.y0
                story = fitz.Story(html="<body>" + block + "</body>", user_css=CSS, archive=archive)
                continue
            story.draw(device)
            top = fitz.Rect(filled).y1 + 2
            if not more:
                break
            writer.end_page(); device, top = writer.begin_page(page_rect), area.y0
    writer.end_page()
    writer.close()
    pdf = fitz.open("pdf", buffer.getvalue())
    for number, page in enumerate(pdf, 1):
        page.insert_font(fontname="kr", fontfile=FONT)
        page.insert_text((page.rect.width - 70, page.rect.height - 22), f"{number} / {pdf.page_count}", fontname="kr", fontsize=8, color=(0.4, 0.4, 0.45))
    pdf.set_metadata({"title": "컴학감동 최종 제출 설계서", "author": "컴학감동"})
    pdf.save(OUT, deflate=True, garbage=3)
    print(OUT, pdf.page_count, "pages")


if __name__ == "__main__":
    main()
