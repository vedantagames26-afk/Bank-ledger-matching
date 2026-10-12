import os
import tempfile
from pathlib import Path
import pytest

os.environ["RECON_RUNTIME"] = tempfile.mkdtemp(prefix="clearledger-tests-")
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GEMINI_MODEL", None)
from backend.app.ingestion import SOURCES, ingest


@pytest.fixture(scope="session")
def dataset():
    root = Path(__file__).resolve().parents[1]
    return {
        s: ingest(s, (root / "data" / f"{s}.csv").read_bytes())["records"]
        for s in SOURCES
    }


@pytest.fixture(scope="session")
def result(dataset):
    from backend.app.engine import reconcile

    return reconcile(dataset)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from backend.app.main import app

    with TestClient(app) as client:
        yield client
