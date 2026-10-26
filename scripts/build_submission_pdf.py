"""Build the submission PDF from the tracked Markdown manuscript."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

IMAGE_RE = re.compile(r"^!\[([^]]+)\]\(([^)]+)\)$")
LINK_RE = re.compile(r"\[([^]]+)\]\(([^)]+)\)")
URL_RE = re.compile(r"(?<![\w/])(https?://[^\s)]+)")


class MainTextEnd(Flowable):
    """Invisible marker retained as a flowable for future layout tooling."""

    def __init__(self) -> None:
        super().__init__()
        self.width = 0
        self.height = 0

    def draw(self) -> None:
        return


def _inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def link(match: re.Match[str]) -> str:
        label = match.group(1).replace("&", "&amp;")
        url = match.group(2).replace('"', "&quot;")
        return f'<link href="{url}" color="#1f5a91">{label}</link>'

    text = LINK_RE.sub(link, text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="7.4">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    text = URL_RE.sub(r'<font color="#1f5a91">\1</font>', text)
    return text


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "SubmissionTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=21,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#17324d"),
            spaceAfter=7,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=10.2,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#444444"),
            spaceAfter=2,
        ),
        "h2": ParagraphStyle(
            "Heading2Custom",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=13.5,
            textColor=colors.HexColor("#17324d"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "Heading3Custom",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.7,
            leading=11.5,
            textColor=colors.HexColor("#244f70"),
            spaceBefore=5,
            spaceAfter=2,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "BodyCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.7,
            leading=10.7,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#202020"),
            spaceAfter=4.2,
            wordWrap="LTR",
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=7.4,
            leading=8.8,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#444444"),
            spaceBefore=2,
            spaceAfter=5,
        ),
        "table": ParagraphStyle(
            "TableText",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8.0,
            wordWrap="CJK",
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=6.8,
            leading=8.0,
            wordWrap="CJK",
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.2,
            leading=8.7,
            leftIndent=5,
            rightIndent=5,
            backColor=colors.HexColor("#f3f5f7"),
            borderColor=colors.HexColor("#d6dce2"),
            borderWidth=0.5,
            borderPadding=4,
        ),
    }


def _table(lines: list[str], styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[Paragraph]] = []
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if index == 1 and all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        style = styles["table_head"] if not rows else styles["table"]
        rows.append([Paragraph(_inline(cell), style) for cell in cells])
    column_count = max(len(row) for row in rows)
    for row in rows:
        row.extend([Paragraph("", styles["table"])] * (column_count - len(row)))
    if column_count >= 9:
        widths = [0.68 * inch] + [0.69 * inch] * (column_count - 1)
    elif column_count == 5:
        widths = [1.58 * inch, 1.0 * inch, 1.2 * inch, 1.42 * inch, 1.34 * inch]
    elif column_count == 4:
        widths = [1.55 * inch, 1.85 * inch, 1.55 * inch, 2.3 * inch]
    else:
        widths = [7.1 * inch / column_count] * column_count
    result = Table(rows, colWidths=widths, repeatRows=1, splitByRow=0, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfeaf2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324d")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aebbc6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return result


def _image(path: Path, caption: str, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    image = Image(str(path))
    max_width = 7.1 * inch
    max_height = 4.25 * inch if path.name == "case_evidence_chain.png" else 3.25 * inch
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    image.hAlign = "CENTER"
    return [Spacer(1, 2), image, Paragraph(_inline(caption), styles["caption"])]


def _parse(source: Path, styles: dict[str, ParagraphStyle]) -> tuple[list[Flowable], int]:
    source_text = source.read_text(encoding="utf-8")
    lines = source_text.splitlines()
    story: list[Flowable] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    abstract_match = re.search(r"\*\*Abstract\.\*\*(.*?)(?:\n\n|$)", source_text, flags=re.DOTALL)
    abstract_words = (
        len(re.findall(r"\b[\w'-]+\b", abstract_match.group(1))) if abstract_match else 0
    )

    def flush() -> None:
        if paragraph:
            text = " ".join(item.strip() for item in paragraph).strip()
            if text:
                story.append(Paragraph(_inline(text), styles["body"]))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("```"):
            flush()
            if in_code and line.strip() == "```":
                story.append(Preformatted("\n".join(code_lines), styles["code"]))
                story.append(Spacer(1, 4))
                code_lines.clear()
                in_code = False
            elif not in_code:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if line.strip() == "<!-- MAIN_TEXT_END -->":
            flush()
            story.append(MainTextEnd())
            story.append(PageBreak())
            index += 1
            continue
        image_match = IMAGE_RE.match(line.strip())
        if image_match:
            flush()
            image_path = (source.parent / image_match.group(2)).resolve()
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            story.extend(_image(image_path, image_match.group(1), styles))
            index += 1
            continue
        if line.startswith("# "):
            flush()
            story.append(Paragraph(_inline(line[2:].strip()), styles["title"]))
            index += 1
            continue
        if line.startswith("## "):
            flush()
            if line[3:].strip() == "Appendix A. Limitations and Dual-Use / Ethical Considerations":
                story.append(PageBreak())
            story.append(Paragraph(_inline(line[3:].strip()), styles["h2"]))
            index += 1
            continue
        if line.startswith("### "):
            flush()
            story.append(Paragraph(_inline(line[4:].strip()), styles["h3"]))
            index += 1
            continue
        if line.startswith("|"):
            flush()
            table_lines: list[str] = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            story.append(_table(table_lines, styles))
            story.append(Spacer(1, 5))
            continue
        if not line.strip():
            flush()
            index += 1
            continue
        if line.startswith(("**Author:", "**Affiliation:", "**Track:", "**Status:")):
            flush()
            story.append(Paragraph(_inline(line), styles["meta"]))
            index += 1
            continue
        paragraph.append(line)
        index += 1
    flush()
    return story, abstract_words


def _footer(canvas: object, document: object) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#c6cdd3"))
    canvas.setLineWidth(0.35)
    canvas.line(0.55 * inch, 0.38 * inch, 7.95 * inch, 0.38 * inch)
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(colors.HexColor("#5d6870"))
    canvas.drawString(0.55 * inch, 0.22 * inch, "Beyond Confessions - Ometere Dele-Alufec")
    canvas.drawRightString(7.95 * inch, 0.22 * inch, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("paper/beyond_confessions_submission.md"))
    parser.add_argument(
        "--output", type=Path, default=Path("output/pdf/beyond_confessions_submission.pdf")
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    story, abstract_words = _parse(args.source, styles)
    frame = Frame(
        0.55 * inch,
        0.52 * inch,
        7.4 * inch,
        10.0 * inch,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="normal",
    )
    doc = BaseDocTemplate(
        str(args.output),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.52 * inch,
        bottomMargin=0.52 * inch,
        title="Beyond Confessions: What Can Message-Action Evidence Really Establish About AI-Agent Collusion?",
        author="Ometere Dele-Alufec",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_footer)])
    doc.build(story)
    reader = PdfReader(str(args.output))
    reference_page = None
    with pdfplumber.open(str(args.output)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if reference_page is None and "References" in text:
                reference_page = page_number
    main_pages = (reference_page - 1) if reference_page else len(reader.pages)
    print(
        {
            "output": str(args.output),
            "pages_total": len(reader.pages),
            "main_text_pages": main_pages,
            "abstract_word_count_approx": abstract_words,
        }
    )
    if abstract_words < 150 or abstract_words > 250:
        raise SystemExit("abstract length is outside 150-250 words")
    if main_pages > 8:
        raise SystemExit("main text exceeds 8 pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
