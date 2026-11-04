import pytest

from adaptive_rag.config import Settings
from adaptive_rag.context import AppContext
from adaptive_rag.db import connect, migrate
from adaptive_rag.vectorstore import VectorStore
from fakes import FakeEmbeddings, FakeLLM


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path / "data", chunking="fixed")


@pytest.fixture
def conn(settings):
    connection = connect(settings.db_path)
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def ctx(settings, conn):
    return AppContext(settings, FakeEmbeddings(), FakeLLM(), VectorStore(settings.chroma_dir))
