"""Test bootstrap.

Each test gets a throwaway SQLite file (see test_app.client_with_db). When
DATABASE_URL points at a Postgres server instead, every test starts from
empty tables so the suite can validate the Postgres engine too.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import database

import pytest


def _flush_tables():
    if not database.database_url():
        return
    database.init_db()
    with database.get_connection() as conn:
        conn.execute("DELETE FROM expenses")
        conn.execute("DELETE FROM budgets")
        conn.execute("DELETE FROM app_users")


@pytest.fixture(autouse=True)
def clean_database():
    _flush_tables()
    yield
    _flush_tables()
