import keyring
import pytest

from adaptive_rag.config import Settings
from adaptive_rag.context import AppContext
from adaptive_rag.db import connect, migrate
from adaptive_rag.vectorstore import VectorStore
from fakes import FakeEmbeddings, FakeLLM, MemoryKeyring


@pytest.fixture
def settings(tmp_path):
    # Keys are pinned to None, so a real key in the developer's shell never reaches a test.
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        chunking="fixed",
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],  # TestClient's default Host
        openai_api_key=None,
        gemini_api_key=None,
        anthropic_api_key=None,
    )


@pytest.fixture(autouse=True)
def memory_keyring():
    """Tests never touch the real OS keychain."""
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def conn(settings):
    connection = connect(settings.db_path)
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def ctx(settings, conn):
    return AppContext(settings, FakeEmbeddings(), FakeLLM(), VectorStore(settings.chroma_dir))
