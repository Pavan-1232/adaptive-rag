"""Stage 4 evaluation systems: A (C1), C7 as a fixed config, and C (optimizer) stay separate."""

from types import SimpleNamespace

from adaptive_rag.evaluation.__main__ import SYSTEMS, _metadata, _settings
from adaptive_rag.evaluation.benchmark import ManifestDocument
from adaptive_rag.evaluation.runner import RESUME_KEYS, build_index, resume_conflicts
from fakes import FakeEmbeddings, FakeLLM

TABLE = "\n".join(
    ["Results by segment", "(in millions)", "2024 2023 2022"]
    + [f"Segment {n} revenue {k},480 {k},509 {k},210" for k, n in enumerate("abcdef", 1)]
)


def test_each_system_gets_its_own_index_folder():
    folders = {mode: _settings("test", "embeddinggemma:300m", mode).data_dir for mode in SYSTEMS}
    assert len(set(folders.values())) == len(folders)
    assert folders["fixed"].name == "test_embeddinggemma_300m"  # Stage 3's folder, unchanged
    assert _settings("test", "embeddinggemma:300m", "C7").chunking == "C7"


def test_metadata_labels_the_system_and_resume_checks_it(tmp_path):
    questions = tmp_path / "q.yaml"
    questions.write_text("[]")
    settings = _settings("test", "m", "C7")
    args = SimpleNamespace(chunking="C7", questions=str(questions), retrieval_only=True)
    meta = _metadata(args, settings, FakeEmbeddings(), "test", "src", "none")
    assert meta["system"].startswith("C7") and meta["chunking"] == "C7"
    assert "chunking" in RESUME_KEYS
    assert resume_conflicts(meta, {**meta, "chunking": "C1"}) == ["chunking"]


def test_forced_c7_indexes_tables_with_the_table_aware_chunker(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "report.txt").write_text("Revenue rose this year.\n\n" + TABLE + "\n")
    settings = _settings("dev", "fake", "C7")
    settings.data_dir = tmp_path / "data"
    documents = [
        ManifestDocument(file="report.txt", set="dev", title="t", url="u", licence="l", sha256="s")
    ]
    ctx, _, indexed = build_index(settings, FakeEmbeddings(), FakeLLM(), documents, root, "kb")
    with ctx.db() as conn:
        strategy = conn.execute(
            "SELECT c.strategy FROM documents d JOIN chunking_configs c"
            " ON c.id = d.chunking_config_id WHERE d.id = ?",
            (indexed["report.txt"]["id"],),
        ).fetchone()[0]
        tables = conn.execute("SELECT SUM(is_table) FROM chunks").fetchone()[0]
    assert strategy == "table_aware" and tables == 1
