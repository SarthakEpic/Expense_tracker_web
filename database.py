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


# ---------------------------------------------------------------------------
# Schema initialization and migrations
# ---------------------------------------------------------------------------


def init_db():
    with get_connection() as conn:
        _initialize(conn)


def _table_exists(conn, table, is_postgres):
    if is_postgres:
        rows = conn.execute(
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_name = ?",
            (table,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name AS name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchall()
    return len(rows) > 0


def _table_columns(conn, table, is_postgres):
    if is_postgres:
        rows = conn.execute(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_name = ?",
            (table,),
        ).fetchall()
    else:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _initialize(conn):
    is_postgres = bool(database_url())
    amount_type = "DOUBLE PRECISION" if is_postgres else "REAL"
    now = datetime.now().strftime(DATE_FORMAT)

    # --- expenses: create fresh or widen legacy single-user tables ---
    if not _table_exists(conn, "expenses", is_postgres):
        conn.execute(
            f"""
            CREATE TABLE expenses (
                id TEXT PRIMARY KEY,
                amount {amount_type} NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL CHECK(category != ''),
                description TEXT DEFAULT '',
                transaction_type TEXT NOT NULL DEFAULT 'expense'
                    CHECK(transaction_type IN ('expense', 'income')),
                status TEXT NOT NULL DEFAULT 'completed'
                    CHECK(status IN ('completed', 'pending')),
                created_at TEXT NOT NULL,
                user_id INTEGER NOT NULL
            )
            """
        )
        user_id_added = False
    else:
        columns = _table_columns(conn, "expenses", is_postgres)
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
        user_id_added = "user_id" not in columns
        if user_id_added:
            conn.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER")

    # --- budgets: rebuild legacy global table to per-user shape ---
    budgets_legacy = _table_exists(conn, "budgets", is_postgres) and (
        "user_id" not in _table_columns(conn, "budgets", is_postgres)
    )
    if budgets_legacy:
        conn.execute("ALTER TABLE budgets RENAME TO budgets_old")
    if not _table_exists(conn, "budgets", is_postgres):
        conn.execute(
            f"""
            CREATE TABLE budgets (
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                monthly_limit {amount_type} NOT NULL CHECK(monthly_limit > 0),
                PRIMARY KEY (user_id, category)
            )
            """
        )

    # --- app_users: rebuild legacy username-keyed table to id-keyed shape ---
    users_legacy = _table_exists(conn, "app_users", is_postgres) and (
        "id" not in _table_columns(conn, "app_users", is_postgres)
    )
    if users_legacy:
        conn.execute("ALTER TABLE app_users RENAME TO app_users_old")
    if not _table_exists(conn, "app_users", is_postgres):
        id_clause = (
            "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
            if is_postgres
            else "id INTEGER PRIMARY KEY"
        )
        conn.execute(
            f"""
            CREATE TABLE app_users (
                {id_clause},
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

    # --- carry legacy users over; the first one becomes the admin ---
    if users_legacy:
        legacy_columns = _table_columns(conn, "app_users_old", is_postgres)
        legacy_users = conn.execute(
            "SELECT username, password_hash FROM app_users_old"
        ).fetchall()
        for index, row in enumerate(legacy_users):
            created = (
                row["created_at"]
                if "created_at" in legacy_columns and row["created_at"]
                else now
            )
            conn.execute(
                "INSERT INTO app_users (username, password_hash, is_admin, created_at) "
                "VALUES (?, ?, ?, ?)",
                (row["username"], row["password_hash"], 1 if index == 0 else 0, created),
            )
        conn.execute("DROP TABLE app_users_old")

    admin_id = _ensure_env_admin(conn, now)

    # --- carry legacy budgets over to the admin ---
    if budgets_legacy:
        conn.execute(
            """
            INSERT INTO budgets (user_id, category, monthly_limit)
            SELECT ?, category, monthly_limit FROM budgets_old
            """,
            (admin_id,),
        )
        conn.execute("DROP TABLE budgets_old")

    # --- claim unowned/orphaned rows (legacy rows and rows of deleted users) ---
    if admin_id is not None:
        conn.execute(
            """
            UPDATE expenses SET user_id = ?
            WHERE user_id IS NULL OR user_id NOT IN (SELECT id FROM app_users)
            """,
            (admin_id,),
        )
        conn.execute(
            """
            UPDATE budgets SET user_id = ?
            WHERE user_id NOT IN (SELECT id FROM app_users)
            """,
            (admin_id,),
        )
        if is_postgres and user_id_added:
            conn.execute("ALTER TABLE expenses ALTER COLUMN user_id SET NOT NULL")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_expenses_type_status "
        "ON expenses(transaction_type, status)"
    )

    if admin_id is not None:
        _ensure_default_budgets(conn, admin_id)


def _ensure_env_admin(conn, now):
    """Seed the first admin from env credentials on an empty users table."""
    count = conn.execute("SELECT COUNT(*) AS total FROM app_users").fetchone()["total"]
    if count > 0:
        row = conn.execute(
            "SELECT id FROM app_users ORDER BY is_admin DESC, id LIMIT 1"
        ).fetchone()
        return row["id"]

    username = os.getenv("APP_USERNAME", "").strip()
    password_hash = os.getenv("APP_PASSWORD_HASH", "").strip()
    if not username or not password_hash:
        return None

    row = conn.execute(
        "INSERT INTO app_users (username, password_hash, is_admin, created_at) "
        "VALUES (?, ?, 1, ?) RETURNING id",
        (username, password_hash, now),
    ).fetchone()
    return row["id"]


def _ensure_default_budgets(conn, user_id):
    count = conn.execute(
        "SELECT COUNT(*) AS total FROM budgets WHERE user_id = ?", (user_id,)
    ).fetchone()["total"]
    if count == 0:
        conn.executemany(
            "INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?)",
            [(user_id, category, limit) for category, limit in DEFAULT_BUDGETS],
        )


def assign_orphan_data(user_id):
    """Attach rows that have no owner (used right after first-account signup)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE expenses SET user_id = ? WHERE user_id IS NULL", (user_id,)
        )
        conn.execute("UPDATE budgets SET user_id = ? WHERE user_id IS NULL", (user_id,))
        _ensure_default_budgets(conn, user_id)


# ---------------------------------------------------------------------------
# CSV migration (legacy import)
# ---------------------------------------------------------------------------


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
        existing_count = conn.execute(
            "SELECT COUNT(*) AS total FROM expenses"
        ).fetchone()["total"]
        if existing_count:
            return

        owner = conn.execute(
            "SELECT id FROM app_users ORDER BY is_admin DESC, id LIMIT 1"
        ).fetchone()
        owner_id = owner["id"] if owner else None
        if owner_id is None:
            return

        with csv_file.open(newline="") as file:
            for row in csv.reader(file):
                expense = parse_csv_row(row)
                if expense:
                    conn.execute(
                        """
                        INSERT INTO expenses
                            (id, amount, category, description, transaction_type,
                             status, created_at, user_id)
                        VALUES (?, ?, ?, ?, 'expense', 'completed', ?, ?)
                        ON CONFLICT(id) DO NOTHING
                        """,
                        (
                            expense["id"],
                            expense["amount"],
                            expense["category"],
                            expense["description"],
                            expense["created_at"],
                            owner_id,
                        ),
                    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def count_users():
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS total FROM app_users").fetchone()["total"]


def create_user(username, password_hash, is_admin=False):
    with get_connection() as conn:
        row = conn.execute(
            "INSERT INTO app_users (username, password_hash, is_admin, created_at) "
            "VALUES (?, ?, ?, ?) RETURNING id",
            (username, password_hash, 1 if is_admin else 0, datetime.now().strftime(DATE_FORMAT)),
        ).fetchone()
        user_id = row["id"]
        _ensure_default_budgets(conn, user_id)
    return user_id


def get_user_by_username(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin FROM app_users WHERE username = ?",
            (username,),
        ).fetchone()
    return row


def get_user_by_id(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin FROM app_users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return row


def list_users():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, is_admin, created_at FROM app_users "
            "ORDER BY is_admin DESC, id"
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_password_hash(username):
    user = get_user_by_username(username)
    return user["password_hash"] if user else None


def update_user_credentials(user_id, new_username, password_hash):
    with get_connection() as conn:
        conn.execute(
            "UPDATE app_users SET username = ?, password_hash = ? WHERE id = ?",
            (new_username, password_hash, user_id),
        )


def set_user_password(user_id, password_hash):
    with get_connection() as conn:
        conn.execute(
            "UPDATE app_users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )


def delete_user(user_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM app_users WHERE id = ?", (user_id,))


# ---------------------------------------------------------------------------
# Expenses (scoped to a user)
# ---------------------------------------------------------------------------


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


def list_expenses(user_id, category=None, month=None, year=None, transaction_type=None, status=None):
    query = """
        SELECT id, amount, category, description, transaction_type, status, created_at
        FROM expenses
        WHERE user_id = ?
    """
    params = [user_id]
    filters = []

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
        query += " AND " + " AND ".join(filters)
    query += " ORDER BY created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_expense(row) for row in rows]


def get_expense(user_id, expense_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, amount, category, description, transaction_type, status, created_at
            FROM expenses
            WHERE user_id = ? AND id = ?
            """,
            (user_id, expense_id),
        ).fetchone()
    return row_to_expense(row) if row else None


def add_expense(
    user_id,
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
                (id, amount, category, description, transaction_type, status, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense_id,
                amount,
                category.strip(),
                description.strip(),
                transaction_type,
                status,
                created_at,
                user_id,
            ),
        )
    return expense_id


def update_expense(
    user_id,
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
            SET amount = ?, category = ?, description = ?, transaction_type = ?,
                status = ?, created_at = ?
            WHERE user_id = ? AND id = ?
            """,
            (
                amount,
                category.strip(),
                description.strip(),
                transaction_type,
                status,
                created_at,
                user_id,
                expense_id,
            ),
        )
    return result.rowcount > 0


def delete_expense(user_id, expense_id):
    with get_connection() as conn:
        result = conn.execute(
            "DELETE FROM expenses WHERE user_id = ? AND id = ?", (user_id, expense_id)
        )
    return result.rowcount > 0


def list_categories(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT category
            FROM expenses
            WHERE user_id = ? AND category != ''
            ORDER BY category
            """,
            (user_id,),
        ).fetchall()
    return [row["category"] for row in rows]


def monthly_totals(user_id, year=None):
    query = """
        SELECT substr(created_at, 1, 7) AS period, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ? AND transaction_type = 'expense' AND status = 'completed'
    """
    params = [user_id]
    if year:
        query += " AND substr(created_at, 1, 4) = ?"
        params.append(year)
    query += " GROUP BY period ORDER BY period"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [(row["period"], row["total"]) for row in rows]


def yearly_totals(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT substr(created_at, 1, 4) AS period, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ? AND transaction_type = 'expense' AND status = 'completed'
            GROUP BY period
            ORDER BY period
            """,
            (user_id,),
        ).fetchall()
    return [(row["period"], row["total"]) for row in rows]


def category_totals(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ? AND transaction_type = 'expense' AND status = 'completed'
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id,),
        ).fetchall()
    return [(row["category"], row["total"]) for row in rows]


# ---------------------------------------------------------------------------
# Budgets (scoped to a user)
# ---------------------------------------------------------------------------


def get_budgets(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT category, monthly_limit FROM budgets WHERE user_id = ? ORDER BY category",
            (user_id,),
        ).fetchall()
    return {row["category"]: float(row["monthly_limit"]) for row in rows}


def set_budget(user_id, category, monthly_limit):
    category = category.strip()
    if not category or monthly_limit <= 0:
        return False
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO budgets (user_id, category, monthly_limit)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit
            """,
            (user_id, category, float(monthly_limit)),
        )
    return True


def delete_budget(user_id, category):
    with get_connection() as conn:
        result = conn.execute(
            "DELETE FROM budgets WHERE user_id = ? AND category = ?",
            (user_id, category.strip()),
        )
    return result.rowcount > 0
