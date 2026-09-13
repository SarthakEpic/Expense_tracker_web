import atexit
import csv
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path


DATABASE_FILE = Path("expenses.db")
CSV_FILE = Path("expenses.csv")
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEFAULT_BUDGETS = [
    ("Food", 12000.0),
    ("Travel", 9000.0),
    ("Shopping", 15000.0),
    ("Bills", 18000.0),
]


def database_url():
    """Postgres connection string, or empty when running on local SQLite."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


_pg_pool = None
_pg_pool_lock = threading.Lock()


def _pg_pool_instance():
    global _pg_pool
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                from psycopg_pool import ConnectionPool
                from psycopg.rows import dict_row

                # Reuse connections across requests (a remote Postgres
                # handshake per query would dominate page latency) and verify
                # connections are alive before use, since Neon suspends idle
                # computes and strands open sockets.
                _pg_pool = ConnectionPool(
                    conninfo=database_url(),
                    min_size=1,
                    max_size=4,
                    max_lifetime=600,
                    max_idle=120,
                    kwargs={"row_factory": dict_row, "prepare_threshold": None},
                    check=ConnectionPool.check_connection,
                    open=True,
                )
    return _pg_pool


def _close_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        _pg_pool.close()
        _pg_pool = None


atexit.register(_close_pg_pool)


def get_connection():
    url = database_url()
    if url:
        pool = _pg_pool_instance()
        return _PgConnection(pool.getconn(), pool)
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


class _PgConnection:
    """sqlite3-shaped wrapper over a pooled psycopg connection.

    Supports exactly the surface this module uses: `with` blocks that commit
    or roll back and then return the connection to the pool, `?` placeholders,
    executemany, and cursors that fetch rows by column name.
    """

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def execute(self, query, params=()):
        return self._conn.execute(query.replace("?", "%s"), tuple(params))

    def executemany(self, query, seq):
        rows = [tuple(params) for params in seq]
        return self._conn.cursor().executemany(query.replace("?", "%s"), rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._pool.putconn(self._conn)
        return False


def init_db():
    if database_url():
        _init_postgres()
        return

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL CHECK(category != ''),
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(expenses)")}
        if "transaction_type" not in columns:
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN transaction_type TEXT NOT NULL "
                "DEFAULT 'expense' CHECK(transaction_type IN ('expense', 'income'))"
            )
        if "status" not in columns:
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN status TEXT NOT NULL "
                "DEFAULT 'completed' CHECK(status IN ('completed', 'pending'))"
            )

        _create_indexes(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                monthly_limit REAL NOT NULL CHECK(monthly_limit > 0)
            )
            """
        )
        _seed_default_budgets(conn)
        _init_app_users(conn)


def _init_postgres():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                amount DOUBLE PRECISION NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL CHECK(category != ''),
                description TEXT DEFAULT '',
                transaction_type TEXT NOT NULL DEFAULT 'expense'
                    CHECK(transaction_type IN ('expense', 'income')),
                status TEXT NOT NULL DEFAULT 'completed'
                    CHECK(status IN ('completed', 'pending')),
                created_at TEXT NOT NULL
            )
            """
        )
        _create_indexes(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                monthly_limit DOUBLE PRECISION NOT NULL CHECK(monthly_limit > 0)
            )
            """
        )
        _seed_default_budgets(conn)
        _init_app_users(conn)


def _init_app_users(conn):
    """Create the credentials table and seed it from env on first boot.

    The env vars remain the bootstrap credential; the Settings page writes
    changes here so they survive restarts without redeployment.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    count = conn.execute("SELECT COUNT(*) AS total FROM app_users").fetchone()["total"]
    username = os.getenv("APP_USERNAME", "").strip()
    password_hash = os.getenv("APP_PASSWORD_HASH", "").strip()
    if count == 0 and username and password_hash:
        conn.execute(
            "INSERT INTO app_users (username, password_hash, updated_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.now().strftime(DATE_FORMAT)),
        )


def get_user_password_hash(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM app_users WHERE username = ?", (username,)
        ).fetchone()
    return row["password_hash"] if row else None


def update_user_credentials(new_username, password_hash, previous_username):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_users (username, password_hash, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                updated_at = excluded.updated_at
            """,
            (new_username, password_hash, datetime.now().strftime(DATE_FORMAT)),
        )
        if new_username != previous_username:
            conn.execute("DELETE FROM app_users WHERE username = ?", (previous_username,))


def _create_indexes(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expenses_type_status ON expenses(transaction_type, status)")


def _seed_default_budgets(conn):
    count = conn.execute("SELECT COUNT(*) AS total FROM budgets").fetchone()["total"]
    if count == 0:
        conn.executemany("INSERT INTO budgets (category, monthly_limit) VALUES (?, ?)", DEFAULT_BUDGETS)


def parse_csv_row(row):
    if len(row) == 5:
        expense_id, amount, category, description, created_at = row
    elif len(row) == 4:
        amount, category, description, created_at = row
        expense_id = str(uuid.uuid4())
    else:
        return None

    try:
        datetime.strptime(created_at, DATE_FORMAT)
        return {
            "id": expense_id,
            "amount": float(amount),
            "category": category.strip(),
            "description": description.strip(),
            "created_at": created_at,
        }
    except (TypeError, ValueError):
        return None


def migrate_csv_to_sqlite(csv_file=CSV_FILE):
    init_db()
    if not csv_file.exists():
        return

    with get_connection() as conn:
        existing_count = conn.execute("SELECT COUNT(*) AS total FROM expenses").fetchone()["total"]
        if existing_count:
            return

        with csv_file.open(newline="") as file:
            for row in csv.reader(file):
                expense = parse_csv_row(row)
                if expense:
                    conn.execute(
                        """
                        INSERT INTO expenses
                            (id, amount, category, description, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO NOTHING
                        """,
                        (
                            expense["id"],
                            expense["amount"],
                            expense["category"],
                            expense["description"],
                            expense["created_at"],
                        ),
                    )


def row_to_expense(row):
    return {
        "id": row["id"],
        "amount": row["amount"],
        "category": row["category"],
        "description": row["description"] or "",
        "transaction_type": row["transaction_type"],
        "status": row["status"],
        "date": row["created_at"],
        "created_at": row["created_at"],
        "date_obj": datetime.strptime(row["created_at"], DATE_FORMAT),
    }


def list_expenses(category=None, month=None, year=None, transaction_type=None, status=None):
    query = """
        SELECT id, amount, category, description, transaction_type, status, created_at
        FROM expenses
    """
    filters = []
    params = []

    if category:
        filters.append("category = ?")
        params.append(category)
    if month:
        filters.append("substr(created_at, 1, 7) = ?")
        params.append(month)
    if year:
        filters.append("substr(created_at, 1, 4) = ?")
        params.append(year)
    if transaction_type:
        filters.append("transaction_type = ?")
        params.append(transaction_type)
    if status:
        filters.append("status = ?")
        params.append(status)

    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_expense(row) for row in rows]


def get_expense(expense_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, amount, category, description, transaction_type, status, created_at
            FROM expenses
            WHERE id = ?
            """,
            (expense_id,),
        ).fetchone()
    return row_to_expense(row) if row else None


def add_expense(
    amount,
    category,
    description="",
    transaction_type="expense",
    status="completed",
    created_at=None,
):
    expense_id = str(uuid.uuid4())
    created_at = created_at or datetime.now().strftime(DATE_FORMAT)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO expenses
                (id, amount, category, description, transaction_type, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense_id,
                amount,
                category.strip(),
                description.strip(),
                transaction_type,
                status,
                created_at,
            ),
        )
    return expense_id


def update_expense(
    expense_id,
    amount,
    category,
    description="",
    transaction_type="expense",
    status="completed",
    created_at=None,
):
    created_at = created_at or datetime.now().strftime(DATE_FORMAT)
    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE expenses
            SET amount = ?, category = ?, description = ?, transaction_type = ?, status = ?, created_at = ?
            WHERE id = ?
            """,
            (
                amount,
                category.strip(),
                description.strip(),
                transaction_type,
                status,
                created_at,
                expense_id,
            ),
        )
    return result.rowcount > 0


def delete_expense(expense_id):
    with get_connection() as conn:
        result = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    return result.rowcount > 0


def list_categories():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT category
            FROM expenses
            WHERE category != ''
            ORDER BY category
            """
        ).fetchall()
    return [row["category"] for row in rows]


def monthly_totals(year=None):
    query = """
        SELECT substr(created_at, 1, 7) AS period, SUM(amount) AS total
        FROM expenses
        WHERE transaction_type = 'expense' AND status = 'completed'
    """
    params = []
    if year:
        query += " AND substr(created_at, 1, 4) = ?"
        params.append(year)
    query += " GROUP BY period ORDER BY period"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [(row["period"], row["total"]) for row in rows]


def yearly_totals():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT substr(created_at, 1, 4) AS period, SUM(amount) AS total
            FROM expenses
            WHERE transaction_type = 'expense' AND status = 'completed'
            GROUP BY period
            ORDER BY period
            """
        ).fetchall()
    return [(row["period"], row["total"]) for row in rows]


def category_totals():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE transaction_type = 'expense' AND status = 'completed'
            GROUP BY category
            ORDER BY total DESC
            """
        ).fetchall()
    return [(row["category"], row["total"]) for row in rows]


def get_budgets():
    with get_connection() as conn:
        rows = conn.execute("SELECT category, monthly_limit FROM budgets ORDER BY category").fetchall()
    return {row["category"]: float(row["monthly_limit"]) for row in rows}


def set_budget(category, monthly_limit):
    category = category.strip()
    if not category or monthly_limit <= 0:
        return False
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO budgets (category, monthly_limit)
            VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit
            """,
            (category, float(monthly_limit)),
        )
    return True


def delete_budget(category):
    with get_connection() as conn:
        result = conn.execute("DELETE FROM budgets WHERE category = ?", (category.strip(),))
    return result.rowcount > 0
