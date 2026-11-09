import sqlite3

import pytest

from adaptive_rag.db import MIGRATIONS_DIR, connect, migrate


def add_kb(conn, name="KB"):
    return conn.execute(
        "INSERT INTO knowledge_bases (name, embedding_provider, embedding_model, embedding_version,"
        " embedding_dimensions, embedding_prompt_version, collection_name)"
        " VALUES (?, 'fake', 'm', 'v', 8, 'p1', ?)",
        (name, f"kb_{name}"),
    ).lastrowid


def add_doc(conn, kb_id, sha="a", filename="a.txt"):
    return conn.execute(
        "INSERT INTO documents (kb_id, filename, format, sha256, size_bytes, status)"
        " VALUES (?, ?, 'txt', ?, 1, 'pending')",
        (kb_id, filename, sha),
    ).lastrowid


def test_migrate_is_idempotent(settings):
    conn = connect(settings.db_path)
    migrate(conn)
    migrate(conn)
    latest = max(int(path.name.split("_", 1)[0]) for path in MIGRATIONS_DIR.glob("*.sql"))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == latest == 8
    conn.close()


def test_same_hash_rejected_within_kb_but_allowed_across_kbs(conn):
    first, second = add_kb(conn, "one"), add_kb(conn, "two")
    add_doc(conn, first)
    add_doc(conn, second)
    with pytest.raises(sqlite3.IntegrityError):
        add_doc(conn, first, filename="copy.txt")


def test_deleting_kb_cascades_to_documents(conn):
    kb_id = add_kb(conn)
    add_doc(conn, kb_id)
    conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_invalid_status_rejected(conn):
    doc_id = add_doc(conn, add_kb(conn))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE documents SET status = 'bogus' WHERE id = ?", (doc_id,))
