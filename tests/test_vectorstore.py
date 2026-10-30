from adaptive_rag.vectorstore import VectorStore, collection_name


def vector(*values):
    return list(values) + [0.0] * (4 - len(values))


def populate(store):
    store.add(
        "kb_a",
        ["1-0", "2-0"],
        [vector(1.0), vector(0.0, 1.0)],
        [{"document_id": 1}, {"document_id": 2}],
    )


def test_collection_name_is_valid_and_identifies_model():
    name = collection_name(12, "embeddinggemma:300m", "85462619ee72")
    assert name == "kb_12__embeddinggemma_85462619"


def test_query_returns_cosine_similarity(settings):
    store = VectorStore(settings.chroma_dir)
    populate(store)
    hits = store.query("kb_a", vector(1.0), 2, [1, 2])
    assert [hit.chunk_id for hit in hits] == ["1-0", "2-0"]
    assert abs(hits[0].score - 1.0) < 1e-6 and abs(hits[1].score) < 1e-6


def test_query_only_searches_given_documents(settings):
    store = VectorStore(settings.chroma_dir)
    populate(store)
    assert [hit.chunk_id for hit in store.query("kb_a", vector(1.0), 5, [2])] == ["2-0"]
    assert store.query("kb_a", vector(1.0), 5, []) == []


def test_collections_are_isolated(settings):
    store = VectorStore(settings.chroma_dir)
    populate(store)
    assert store.query("kb_b", vector(1.0), 5, [1, 2]) == []


def test_data_persists_across_clients(settings):
    populate(VectorStore(settings.chroma_dir))
    assert VectorStore(settings.chroma_dir).document_counts("kb_a") == {1: 1, 2: 1}
