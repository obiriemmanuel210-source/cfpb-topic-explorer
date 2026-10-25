import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db  # noqa: E402

# Tests always run on in-memory SQLite. Set TEST_DATABASE_URL to a throwaway
# Postgres database to run them on Postgres as well, e.g.
#   TEST_DATABASE_URL=postgresql://postgres@localhost:5432/church_test
BACKENDS = ["sqlite"] + (["postgres"] if os.environ.get("TEST_DATABASE_URL") else [])


@pytest.fixture(params=BACKENDS)
def conn(request):
    if request.param == "sqlite":
        yield db.connect(":memory:")
        return
    engine = db.connect(os.environ["TEST_DATABASE_URL"])
    yield engine
    with engine.begin() as c:  # wipe everything so each test starts clean
        names = ", ".join(f'"{t.name}"' for t in db.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    engine.dispose()
