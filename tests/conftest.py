import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def tmp_music_dir(tmp_path):
    d = tmp_path / "music"
    d.mkdir()
    return d
