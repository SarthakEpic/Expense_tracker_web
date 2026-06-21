import csv
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


DATABASE_FILE = Path("expenses.db")
CSV_FILE = Path("expenses.csv")
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL,
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
        existing_count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        if existing_count:
            return

        with csv_file.open(newline="") as file:
            for row in csv.reader(file):
                expense = parse_csv_row(row)
                if expense:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO expenses
                            (id, amount, category, description, created_at)
                        VALUES (?, ?, ?, ?, ?)
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
        filters.append("strftime('%Y-%m', created_at) = ?")
        params.append(month)
    if year:
        filters.append("strftime('%Y', created_at) = ?")
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
        SELECT strftime('%Y-%m', created_at) AS period, SUM(amount) AS total
        FROM expenses
    """
    params = []
    if year:
        query += " WHERE strftime('%Y', created_at) = ?"
        params.append(year)
    query += " GROUP BY period ORDER BY period"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [(row["period"], row["total"]) for row in rows]


def yearly_totals():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT strftime('%Y', created_at) AS period, SUM(amount) AS total
            FROM expenses
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
            GROUP BY category
            ORDER BY total DESC
            """
        ).fetchall()
    return [(row["category"], row["total"]) for row in rows]
