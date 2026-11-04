import pytest

from adaptive_rag.evaluation.benchmark import BenchmarkQuestion, load_manifest, load_questions
from adaptive_rag.evaluation.metrics import (
    RankedChunk,
    Span,
    evidence_recall,
    hit_at_k,
    recall_at_budget,
    recall_at_k,
    reciprocal_rank,
)
from adaptive_rag.evaluation.questions import (
    rejection_reason,
    sample_windows,
    word_overlap,
)
from adaptive_rag.evaluation.spans import locate_quote, page_range
from adaptive_rag.evaluation.stats import is_tie, mean_ci, paired_difference_ci
from adaptive_rag.loaders import ExtractedDocument, Unit


def chunk(start, end, tokens=100, document="a"):
    return RankedChunk(document, start, end, tokens)


EVIDENCE = [Span("a", 100, 200)]


# Hand-calculated expected values.
def test_hit_needs_half_of_the_evidence():
    assert hit_at_k([chunk(0, 150)], EVIDENCE, 5) == 1.0
    assert hit_at_k([chunk(0, 149)], EVIDENCE, 5) == 0.0


def test_hit_only_counts_within_k():
    assert hit_at_k([chunk(0, 10), chunk(100, 200)], EVIDENCE, 1) == 0.0
    assert hit_at_k([chunk(0, 10), chunk(100, 200)], EVIDENCE, 2) == 1.0


def test_same_offsets_in_another_document_do_not_count():
    assert hit_at_k([chunk(100, 200, document="b")], EVIDENCE, 5) == 0.0
    assert evidence_recall([chunk(100, 200, document="b")], EVIDENCE) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank([chunk(0, 10), chunk(0, 10), chunk(100, 200)], EVIDENCE) == 1 / 3
    assert reciprocal_rank([chunk(0, 10)], EVIDENCE) == 0.0


def test_recall_doesnt_double_count_overlapping_chunks():
    assert evidence_recall([chunk(100, 150), chunk(120, 170)], EVIDENCE) == 0.7
    assert evidence_recall([chunk(0, 500), chunk(100, 200)], EVIDENCE) == 1.0


def test_recall_across_multiple_evidence_spans():
    evidence = [Span("a", 0, 100), Span("b", 0, 300)]
    assert evidence_recall([chunk(0, 100)], evidence) == 0.25
    assert recall_at_k([chunk(0, 100), chunk(0, 300, document="b")], evidence, 1) == 0.25
    assert recall_at_k([chunk(0, 100), chunk(0, 300, document="b")], evidence, 2) == 1.0


def test_any_alternative_covers_the_required_fact():
    required = Span("a", 100, 200, alternatives=(Span("b", 0, 50),))
    assert evidence_recall([chunk(0, 50, document="b")], [required]) == 1.0
    assert evidence_recall([chunk(100, 150)], [required]) == 0.5
    assert evidence_recall([chunk(100, 150), chunk(0, 50, document="b")], [required]) == 1.0
    assert evidence_recall([chunk(500, 600)], [required]) == 0.0
    assert hit_at_k([chunk(0, 50, document="b")], [required], 1) == 1.0


def test_two_required_facts_both_count_when_one_has_alternatives():
    first = Span("a", 0, 100, alternatives=(Span("b", 0, 100),))
    second = Span("a", 200, 300)
    assert evidence_recall([chunk(0, 100, document="b")], [first, second]) == 0.5


def test_recall_at_budget_charges_for_tokens():
    small = [chunk(0, 50, tokens=100), chunk(100, 200, tokens=100)]
    large = [chunk(0, 90, tokens=300), chunk(100, 200, tokens=300)]
    assert recall_at_budget(small, EVIDENCE, 200) == 1.0
    assert recall_at_budget(large, EVIDENCE, 300) == 0.0


def test_recall_at_budget_stops_at_first_chunk_that_does_not_fit():
    chunks = [chunk(0, 10, tokens=150), chunk(0, 10, tokens=100), chunk(100, 200, tokens=10)]
    assert recall_at_budget(chunks, EVIDENCE, 200) == 0.0


def test_quote_location_ignores_case_and_whitespace():
    text = "Intro. Revenue grew\nEIGHT  percent this year. End."
    start, end = locate_quote(text, "revenue grew eight percent this year.")
    assert text[start:end] == "Revenue grew\nEIGHT  percent this year."


def test_quote_location_tolerates_a_copied_line_break_hyphen():
    text = "Systems use semantic chunking widely."
    start, end = locate_quote(text, "use seman- tic chunking")
    assert text[start:end] == "use semantic chunking"


def test_quote_location_prefers_the_stated_page_for_repeated_rows():
    text = "Credits 2,763 1,790\f Other\f Credits 2,763 1,790 end"
    second = text.index("Credits", 5)
    assert locate_quote(text, "credits 2,763 1,790", (second - 2, len(text)))[0] == second
    # No match on the preferred page: fall back to the first match, as before.
    assert locate_quote(text, "credits 2,763 1,790", (8, 12))[0] == 0
    assert locate_quote(text, "credits 2,763 1,790")[0] == 0


def test_page_range_reads_stored_and_extracted_units():
    units = [{"number": 1, "start": 0, "end": 10}, {"number": 2, "start": 11, "end": 20}]
    assert page_range(units, 2) == (11, 20)
    assert page_range(units, 9) is None
    assert page_range(units, None) is None


def test_missing_quote_returns_none():
    assert locate_quote("Some text.", "Not present") is None
    assert locate_quote("Some text.", "   ") is None


def test_mean_ci_contains_the_mean_and_is_reproducible():
    values = [0.0, 1.0] * 20
    assert mean_ci(values) == mean_ci(values)
    mean, low, high = mean_ci(values)
    assert mean == 0.5 and low < 0.5 < high


def test_identical_systems_tie_and_clearly_different_ones_do_not():
    first = [1.0, 0.0] * 20
    assert is_tie(paired_difference_ci(first, first))
    assert not is_tie(paired_difference_ci([1.0] * 40, [0.0] * 40))


def test_paired_difference_needs_equal_lengths():
    with pytest.raises(ValueError):
        paired_difference_ci([1.0], [1.0, 0.0])


def test_word_overlap():
    assert word_overlap("revenue growth", "revenue growth was high") == 1.0
    assert word_overlap("how did sales change", "revenue rose") == 0.0


@pytest.mark.parametrize(
    ("question", "quote", "reason"),
    [
        ("What changed in sales?", "Short.", "quote too short"),
        ("What changed in sales?", "This sentence is not in the window at all.", "quote not found"),
        (
            "Revenue grew by how much in fiscal year?",
            "Revenue grew by eight percent in fiscal year.",
            "copies",
        ),
        (
            "What does the passage say about sales?",
            "Revenue grew by eight percent in fiscal year.",
            "refers",
        ),
        ("x" * 201 + " sales", "Revenue grew by eight percent in fiscal year.", "too long"),
    ],
)
def test_rejection_reasons(question, quote, reason):
    window = "Opening text. Revenue grew by eight percent in fiscal year. Closing text."
    assert reason in rejection_reason(question, quote, window)


def test_good_question_passes_filters():
    window = "Revenue grew by eight percent in fiscal year."
    assert rejection_reason("How fast did sales expand?", window, window) is None


def test_windows_cover_the_document_evenly():
    doc = ExtractedDocument("x" * 10_000, "page", [Unit(1, 0, 10_000)])
    windows = sample_windows(doc, 5)
    assert windows[0][0] == 0 and windows[-1][1] == 10_000
    assert len(windows) == 5


def test_short_document_gets_one_window():
    doc = ExtractedDocument("short", "page", [Unit(1, 0, 5)])
    assert sample_windows(doc, 5) == [(0, 5)]


def question(**overrides):
    values = {
        "id": "q1",
        "document": "a.pdf",
        "type": "factual",
        "question": "What happened?",
        "answerable": True,
        "evidence": [{"page": 1, "quote": "It happened."}],
    }
    return BenchmarkQuestion(**{**values, **overrides})


def test_template_rules_are_enforced():
    assert question().answerable
    with pytest.raises(ValueError, match="need evidence"):
        question(evidence=[])
    with pytest.raises(ValueError, match="can't have evidence"):
        question(answerable=False, type="near_miss")
    with pytest.raises(ValueError, match="is for answerable"):
        question(answerable=False, type="factual", evidence=[])
    with pytest.raises(ValueError, match="is for unanswerable"):
        question(type="near_miss")


def test_duplicate_question_ids_rejected(tmp_path):
    path = tmp_path / "q.yaml"
    item = (
        "- {id: a, document: a.pdf, type: near_miss, question: 'Is this absent?', "
        "answerable: false}\n"
    )
    path.write_text(item * 2)
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(path)


def test_manifest_separates_dev_and_test_documents():
    documents = load_manifest()
    dev = {item.name for item in documents if item.set == "dev"}
    test = {item.name for item in documents if item.set == "test"}
    assert len(dev) == 4 and len(test) == 5 and not dev & test
