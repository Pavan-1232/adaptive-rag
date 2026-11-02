"""Builders for test documents, so no binary fixtures live in the repo."""

from pathlib import Path

import docx
from fpdf import FPDF


def make_pdf(path: Path, pages: list[list[tuple[str, int]]], footer: bool = False) -> Path:
    """Each page is a list of (text, font_size) lines."""
    pdf = FPDF()
    pdf.set_auto_page_break(False)
    for number, lines in enumerate(pages, start=1):
        pdf.add_page()
        pdf.set_y(15)
        for text, size in lines:
            pdf.set_font("Helvetica", size=size)
            pdf.multi_cell(0, size * 0.6, text, new_x="LMARGIN", new_y="NEXT")
        if footer:
            pdf.set_y(280)
            pdf.set_font("Helvetica", size=8)
            pdf.cell(0, 5, f"Acme Annual Report - Page {number}")
    pdf.output(str(path))
    return path


def make_two_column_pdf(path: Path, title: str, left: str, right: str) -> Path:
    """A full-width title over two independent columns, like a conference paper."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=18)
    pdf.set_xy(10, 15)
    pdf.cell(190, 10, title, align="C")
    pdf.set_font("Helvetica", size=10)
    pdf.set_xy(10, 35)
    pdf.multi_cell(85, 5, left)
    pdf.set_xy(110, 35)
    pdf.multi_cell(85, 5, right)
    pdf.output(str(path))
    return path


def make_table_pdf(path: Path, rows: list[tuple[str, str]]) -> Path:
    """A financial-style table: short labels on the left, numbers far to the right."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for index, (label, values) in enumerate(rows):
        y = 20 + index * 6
        pdf.text(15, y, label)
        pdf.text(120, y, values)
    pdf.output(str(path))
    return path


def make_pdf_with_rotated_stamp(path: Path, body: str, stamp: str) -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(20, 20)
    pdf.multi_cell(160, 6, body)
    with pdf.rotation(90, x=10, y=200):
        pdf.text(10, 200, stamp)
    pdf.output(str(path))
    return path


def make_scanned_pdf(path: Path, page_count: int = 2) -> Path:
    pdf = FPDF()
    for _ in range(page_count):
        pdf.add_page()
        pdf.rect(20, 20, 100, 100, style="F")
    pdf.output(str(path))
    return path


def make_encrypted_pdf(path: Path) -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Secret content that nobody should be able to read.")
    pdf.set_encryption(owner_password="owner", user_password="user")  # noqa: S106
    pdf.output(str(path))
    return path


def make_docx(path: Path, blocks: list[tuple[str, str]], table: list[list[str]] | None = None):
    """Each block is (style, text); a style of 'Heading 1' makes a heading."""
    document = docx.Document()
    for style, text in blocks:
        document.add_paragraph(text, style=style)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for col_index, value in enumerate(row):
                grid.cell(row_index, col_index).text = value
    document.save(str(path))
    return path
