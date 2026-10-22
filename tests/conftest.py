from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="aidash-test-"))
os.environ["AIDASH_DATA_DIR"] = str(_TMP / "data")
os.environ["AIDASH_KEY_PATH"] = str(_TMP / "key")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from standalone.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_db():
    from standalone.db import init_db

    init_db()
    yield
    from standalone.db import _connect

    conn = _connect()
    try:
        conn.execute("DELETE FROM accounts")
        conn.commit()
    finally:
        conn.close()
