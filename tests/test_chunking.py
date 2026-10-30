import pytest

from adaptive_rag.chunking import chunk_fixed, count_tokens
from adaptive_rag.loaders import ExtractedDocument, Section, Unit


def doc_from_lines(lines: list[str], sections=()) -> ExtractedDocument:
    text = "\n".join(lines)
    units, offset = [], 0
    for number, line in enumerate(lines, start=1):
        units.append(Unit(number, offset, offset + len(line)))
        offset += len(line) + 1
    return ExtractedDocument(text, "line", units, list(sections))


def long_doc(count=300):
    return doc_from_lines([f"Sentence number {i} about quarterly revenue." for i in range(count)])


def test_chunk_text_matches_its_offsets():
    doc = long_doc()
    chunks = chunk_fixed(doc, size=50, overlap=5)
    assert len(chunks) > 1
    for chunk in chunks:
        assert doc.text[chunk.start : chunk.end] == chunk.text


def test_offsets_hold_for_multibyte_text():
    doc = doc_from_lines(["你好世界 🙂 café naïve 日本語のテキスト"] * 200)
    chunks = chunk_fixed(doc, size=40, overlap=4)
    for chunk in chunks:
        assert doc.text[chunk.start : chunk.end] == chunk.text
    assert chunks[-1].end == len(doc.text)


def test_chunks_cover_all_text_and_overlap():
    doc = long_doc()
    chunks = chunk_fixed(doc, size=50, overlap=5)
    assert chunks[0].start == 0 and chunks[-1].end == len(doc.text)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start < previous.end


def test_indexes_are_sequential_and_sizes_respected():
    chunks = chunk_fixed(long_doc(), size=50, overlap=5)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.token_count <= 50 for chunk in chunks)
    assert all(count_tokens(chunk.text) <= 52 for chunk in chunks)


def test_locators_point_to_the_units_containing_the_chunk():
    doc = long_doc()
    for chunk in chunk_fixed(doc, size=50, overlap=5):
        first = doc.units[chunk.locator_start - 1]
        last = doc.units[chunk.locator_end - 1]
        assert first.start <= chunk.start < first.end + 1
        assert last.start < chunk.end <= last.end + 1


def test_locator_skips_a_gap_between_units():
    doc = ExtractedDocument("aaaa\n\nbbbb", "page", [Unit(1, 0, 4), Unit(3, 6, 10)])
    from adaptive_rag.chunking.base import locate

    assert locate(doc, 4, 10) == (3, 3)
    assert locate(doc, 0, 10) == (1, 3)
    assert locate(doc, 0, 3) == (1, 1)


def test_section_heading_is_recorded():
    doc = long_doc(100)
    middle = len(doc.text) // 2
    doc.sections = [Section("First", 0, middle), Section("Second", middle, len(doc.text))]
    chunks = chunk_fixed(doc, size=50, overlap=0)
    assert chunks[0].section_heading == "First"
    assert chunks[-1].section_heading == "Second"


def test_text_before_first_heading_has_no_section():
    doc = long_doc(100)
    doc.sections = [Section("Late", len(doc.text) - 5, len(doc.text))]
    assert chunk_fixed(doc, size=50, overlap=0)[0].section_heading is None


def test_short_document_gives_one_chunk():
    chunks = chunk_fixed(doc_from_lines(["Just one short line."]))
    assert len(chunks) == 1 and chunks[0].text == "Just one short line."


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (1025, 0), (50, 50), (50, -1)])
def test_invalid_settings_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunk_fixed(long_doc(5), size=size, overlap=overlap)
