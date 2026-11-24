import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "teste.db"
os.environ["MINEPLAN_DB_URL"] = f"sqlite:///{_tmp}"
os.environ.pop("MINEPLAN_POWERBI_TOKEN", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
