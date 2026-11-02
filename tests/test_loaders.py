import zipfile

import pytest

from adaptive_rag.loaders import LOADERS, ExtractionError, UploadRejected, validate_upload
from adaptive_rag.loaders.pdf import _is_bold_font, _join_hyphenated
from documents import (
    make_docx,
    make_encrypted_pdf,
    make_pdf,
    make_pdf_with_rotated_stamp,
    make_scanned_pdf,
    make_table_pdf,
    make_two_column_pdf,
)

BODY = "The quick brown fox reports revenue growth across every region this year"


def unit_text(doc, number):
    unit = next(u for u in doc.units if u.number == number)
    return doc.text[unit.start : unit.end]


def test_pdf_page_units_map_to_the_right_text(tmp_path):
    pages = [[("Alpha page text " * 3, 11)], [("Beta page text " * 3, 11)]]
    path = make_pdf(tmp_path / "a.pdf", pages)
    doc = LOADERS["pdf"].extract(path)
    assert doc.locator_kind == "page"
    assert [u.number for u in doc.units] == [1, 2]
    assert "Alpha" in unit_text(doc, 1) and "Beta" not in unit_text(doc, 1)
    assert "Beta" in unit_text(doc, 2) and "Alpha" not in unit_text(doc, 2)


def test_pdf_detects_headings_from_font_size(tmp_path):
    pages = [[("Market Overview", 20), (BODY, 11), (BODY, 11), ("Risk Factors", 20), (BODY, 11)]]
    doc = LOADERS["pdf"].extract(make_pdf(tmp_path / "a.pdf", pages))
    assert [s.heading for s in doc.sections] == ["Market Overview", "Risk Factors"]
    first, second = doc.sections
    assert doc.text[first.start :].startswith("Market Overview")
    assert first.end == second.start and second.end == len(doc.text)


def test_pdf_removes_running_footers(tmp_path):
    topics = ["revenue", "margins", "hiring", "suppliers", "pricing"]
    pages = [[(f"This page covers {topic} in some detail", 11)] for topic in topics]
    doc = LOADERS["pdf"].extract(make_pdf(tmp_path / "a.pdf", pages, footer=True))
    assert "Annual Report" not in doc.text
    assert all(topic in doc.text for topic in topics)


def test_pdf_blank_page_warns_and_keeps_page_numbers_correct(tmp_path):
    pages = [[(BODY, 11)], [(BODY, 11)], [], [("Final page content goes right here", 11)]]
    doc = LOADERS["pdf"].extract(make_pdf(tmp_path / "a.pdf", pages))
    assert [u.number for u in doc.units] == [1, 2, 4]
    assert "Final" in unit_text(doc, 4)
    assert any("3" in warning for warning in doc.warnings)


def test_two_column_pdf_reads_each_column_in_order(tmp_path):
    left = " ".join(f"leftword{i}" for i in range(120))
    right = " ".join(f"rightword{i}" for i in range(120))
    path = make_two_column_pdf(tmp_path / "a.pdf", "A Full Width Paper Title", left, right)
    doc = LOADERS["pdf"].extract(path)
    assert doc.text.startswith("A Full Width Paper Title")
    positions = [doc.text.index(f"leftword{i}") for i in range(120)]
    assert positions == sorted(positions)
    assert doc.text.index("leftword119") < doc.text.index("rightword0")
    assert doc.text.count("A Full Width Paper Title") == 1


def test_table_row_stays_with_its_numbers(tmp_path):
    rows = [(f"Line item number {i}", f"{i},111 {i},222 {i},333 {i} %") for i in range(30)]
    rows[10] = ("Total revenues", "97,690 96,773 81,462 1 %")
    doc = LOADERS["pdf"].extract(make_table_pdf(tmp_path / "a.pdf", rows))
    assert "Total revenues 97,690 96,773 81,462 1 %" in doc.text


def test_rotated_margin_stamp_is_dropped(tmp_path):
    path = make_pdf_with_rotated_stamp(tmp_path / "a.pdf", "Plain body text " * 10, "STAMPTEXT")
    doc = LOADERS["pdf"].extract(path)
    assert "Plain body text" in doc.text and "STAMPTEXT" not in doc.text


def test_single_column_page_is_not_split(tmp_path):
    sentence = "Revenue grew across every region and the margin expanded again this year. "
    doc = LOADERS["pdf"].extract(make_pdf(tmp_path / "a.pdf", [[(sentence * 12, 11)]]))
    lines = [line for line in doc.text.split("\n") if line]
    assert len(lines[0].split()) > 8  # Lines run across the page's full width.


def test_words_split_by_line_break_hyphens_are_repaired():
    lines = [{"text": "popularized se-"}, {"text": "mantic chunking well-"}, {"text": "Known term"}]
    joined = _join_hyphenated(lines)
    assert [line["text"] for line in joined] == [
        "popularized semantic",
        "chunking well-",
        "Known term",
    ]


def test_hyphen_repair_drops_a_line_left_empty():
    assert [line["text"] for line in _join_hyphenated([{"text": "re-"}, {"text": "port"}])] == [
        "report"
    ]


@pytest.mark.parametrize("font", ["Helvetica-Bold", "NimbusRomNo9L-Medi", "Arial-Black"])
def test_bold_fonts_are_recognized(font):
    assert _is_bold_font(font)


def test_scanned_pdf_fails_with_ocr_message(tmp_path):
    with pytest.raises(ExtractionError, match="OCR"):
        LOADERS["pdf"].extract(make_scanned_pdf(tmp_path / "scan.pdf"))


def test_encrypted_pdf_fails_clearly(tmp_path):
    with pytest.raises(ExtractionError, match="password"):
        LOADERS["pdf"].extract(make_encrypted_pdf(tmp_path / "secret.pdf"))


def test_corrupt_pdf_fails_clearly(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not really a pdf")
    with pytest.raises(ExtractionError):
        LOADERS["pdf"].extract(path)


def test_docx_paragraphs_headings_and_tables(tmp_path):
    path = make_docx(
        tmp_path / "a.docx",
        [
            ("Heading 1", "Strategy"),
            ("Normal", "First paragraph."),
            ("Normal", ""),
            ("Heading 2", "Pricing"),
            ("Normal", "Second paragraph."),
        ],
        table=[["Region", "Sales"], ["EMEA", "10"]],
    )
    doc = LOADERS["docx"].extract(path)
    assert doc.locator_kind == "paragraph"
    assert [s.heading for s in doc.sections] == ["Strategy", "Pricing"]
    assert unit_text(doc, 2) == "First paragraph."
    assert unit_text(doc, 4) == "Second paragraph."
    assert "EMEA | 10" in unit_text(doc, 5)


def test_empty_docx_fails(tmp_path):
    with pytest.raises(ExtractionError):
        LOADERS["docx"].extract(make_docx(tmp_path / "a.docx", []))


def test_txt_line_numbers_survive_blank_lines_and_crlf(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes(b"# Intro\r\nline two\r\n\r\nline four\r\n")
    doc = LOADERS["txt"].extract(path)
    assert doc.locator_kind == "line"
    assert [u.number for u in doc.units] == [1, 2, 4]
    assert unit_text(doc, 4) == "line four"
    assert [s.heading for s in doc.sections] == ["Intro"]


def test_txt_non_utf8_decodes_with_warning(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes("caf\xe9 society".encode("latin-1"))
    doc = LOADERS["txt"].extract(path)
    assert "café" in doc.text and doc.warnings


def test_blank_txt_fails(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("  \n\n ")
    with pytest.raises(ExtractionError):
        LOADERS["txt"].extract(path)


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("a.exe", b"MZ", "Unsupported"),
        ("a.pdf", b"not a pdf at all", "not a valid PDF"),
        ("a.docx", b"not a zip", "not a valid DOCX"),
        ("a.txt", b"bin\x00ary", "binary"),
        ("a.txt", b"", "empty"),
    ],
)
def test_validation_rejects_bad_files(tmp_path, filename, content, message):
    path = tmp_path / "upload"
    path.write_bytes(content)
    with pytest.raises(UploadRejected, match=message):
        validate_upload(path, filename, 1024)


def test_validation_rejects_oversized_file(tmp_path):
    path = tmp_path / "upload"
    path.write_bytes(b"x" * 2048)
    with pytest.raises(UploadRejected, match="limit"):
        validate_upload(path, "a.txt", 1024)


def test_validation_rejects_zip_that_is_not_docx(tmp_path):
    path = tmp_path / "upload"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "hi")
    with pytest.raises(UploadRejected, match="not a valid DOCX"):
        validate_upload(path, "a.docx", 1024 * 1024)


def test_validation_accepts_uppercase_extension(tmp_path):
    path = make_docx(tmp_path / "a.docx", [("Normal", "Hello")])
    assert validate_upload(path, "REPORT.DOCX", 10 * 1024 * 1024) == "docx"
