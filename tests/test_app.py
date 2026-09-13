import hashlib
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_TEST_DIGEST = hashlib.pbkdf2_hmac("sha256", b"secret", b"testsalt", 120_000).hex()
os.environ.setdefault(
    "APP_PASSWORD_HASH", f"pbkdf2_sha256$120000$testsalt${_TEST_DIGEST}"
)
os.environ.setdefault("APP_USERNAME", "admin")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.append(str(Path(__file__).resolve().parents[1]))

import database
import main
from fastapi.testclient import TestClient


def admin_id():
    return database.get_user_by_username("admin")["id"]


def client_with_db(tmp_path):
    database.DATABASE_FILE = tmp_path / "expenses.db"
    database.CSV_FILE = tmp_path / "expenses.csv"
    main.PASSWORD_HASH = main.hash_password("secret", salt="testsalt")
    database.init_db()
    return TestClient(main.app)


def csrf_from_login_page(client):
    response = client.get("/login")
    assert response.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def login(client):
    token = csrf_from_login_page(client)
    response = client.post(
        "/login",
        data={
            "username": "admin",
            "password": "secret",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302


def page_csrf(response):
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def add_sample_expense(
    client, category="Food", transaction_type="expense", status="completed"
):
    response = client.get("/")
    token = page_csrf(response)
    response = client.post(
        "/add",
        data={
            "amount": "120.50",
            "category": category,
            "description": "Lunch",
            "transaction_type": transaction_type,
            "status": status,
            "transaction_date": "2026-06-10T10:00",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    return database.list_expenses(admin_id())[0]


def test_health_endpoint(tmp_path):
    client = client_with_db(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_add_edit_delete_expense(tmp_path):
    client = client_with_db(tmp_path)
    login(client)
    expense = add_sample_expense(client)
    response = client.get("/")
    assert "Expense Tracker" in response.text
    assert "Welcome back Admin" in response.text
    assert "Current Balance" in response.text
    assert "Spendical" not in response.text
    assert "Capital M" not in response.text
    assert "Food" in response.text
    assert "120.50" in response.text
    assert "Completed" in response.text
    assert "Expense" in response.text

    edit_page = client.get(f"/edit/{expense['id']}")
    token = page_csrf(edit_page)
    response = client.post(
        f"/edit/{expense['id']}",
        data={
            "amount": "99.99",
            "category": "Travel",
            "description": "Cab",
            "transaction_type": "expense",
            "status": "completed",
            "transaction_date": "2026-06-11T09:30",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert database.get_expense(admin_id(), expense["id"])["category"] == "Travel"

    home = client.get("/")
    token = page_csrf(home)
    response = client.post(
        f"/delete/{expense['id']}",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert database.list_expenses(admin_id()) == []


def test_csrf_blocks_mutating_request(tmp_path):
    client = client_with_db(tmp_path)
    login(client)
    response = client.post(
        "/add",
        data={"amount": "12", "category": "Food", "description": "Missing token"},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert database.list_expenses(admin_id()) == []


def test_filters_and_export(tmp_path):
    client = client_with_db(tmp_path)
    login(client)
    add_sample_expense(client, category="Food")
    add_sample_expense(client, category="Bills")

    response = client.get("/?category=Food")
    assert "Food" in response.text
    assert "Current Balance" in response.text
    assert "₹120.50" in response.text
    assert "Bills" not in response.text or "₹241" not in response.text

    export = client.get("/export?category=Food")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "Food" in export.text
    assert "Bills" not in export.text
    assert export.text.startswith("type,status,amount,category,description,date")


def test_income_pending_and_projection_are_real_calculations(tmp_path):
    client = client_with_db(tmp_path)
    login(client)
    add_sample_expense(client, category="Salary", transaction_type="income")
    add_sample_expense(client, category="Travel", status="pending")

    response = client.get("/")
    assert "Income" in response.text
    assert "+₹120.50" in response.text
    assert "pending transactions" in response.text
    assert "status-pending" in response.text

    transactions = [
        {
            "amount": 100,
            "category": "Food",
            "date": "2026-06-05 10:00:00",
            "transaction_type": "expense",
            "status": "completed",
        },
        {
            "amount": 500,
            "category": "Salary",
            "date": "2026-06-06 10:00:00",
            "transaction_type": "income",
            "status": "completed",
        },
        {
            "amount": 75,
            "category": "Bills",
            "date": "2026-06-07 10:00:00",
            "transaction_type": "expense",
            "status": "pending",
        },
    ]
    summary = main.summarize_expenses(transactions, now=datetime(2026, 6, 10))
    assert summary["total_spent"] == 100
    assert summary["total_income"] == 500
    assert summary["pending_total"] == 75
    assert summary["projected_spending"] == 300
    assert summary["monthly_spending"][0]["projection"] == 200


def test_page_routes_render(tmp_path):
    client = client_with_db(tmp_path)
    login(client)

    for route in ["/transactions", "/analytics", "/budgets", "/reports", "/settings", "/coming-soon"]:
        response = client.get(route)
        assert response.status_code == 200


def test_open_redirect_blocked(tmp_path):
    client = client_with_db(tmp_path)
    login(client)
    home = client.get("/")
    token = page_csrf(home)

    response = client.post(
        "/add",
        data={
            "amount": "50.00",
            "category": "Food",
            "description": "Snack",
            "transaction_type": "expense",
            "status": "completed",
            "transaction_date": "2026-06-10T10:00",
            "csrf_token": token,
        },
        headers={"referer": "https://evil.com/steal-creds"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_percent_change_with_negative_previous():
    assert main.percent_change(200, -100) == 300.0
    assert main.percent_change(0, 100) == -100.0
    assert main.percent_change(150, 100) == 50.0


def test_dynamic_budget_endpoints(tmp_path):
    client = client_with_db(tmp_path)
    login(client)
    page = client.get("/budgets")
    token = page_csrf(page)

    response = client.post(
        "/budgets/set",
        data={
            "category": "Entertainment",
            "monthly_limit": "5000",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert database.get_budgets(admin_id())["Entertainment"] == 5000.0

    budgets_page = client.get("/budgets")
    assert "Entertainment" in budgets_page.text
    token = page_csrf(budgets_page)

    delete_resp = client.post(
        "/budgets/delete/Entertainment",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert delete_resp.status_code == 302
    assert "Entertainment" not in database.get_budgets(admin_id())


def test_env_credentials_seeded_into_database(tmp_path):
    client_with_db(tmp_path)
    assert database.get_user_password_hash("admin") == os.environ["APP_PASSWORD_HASH"]


def test_change_credentials_flow(tmp_path):
    client = client_with_db(tmp_path)
    login(client)

    settings_page = client.get("/settings")
    assert "Login credentials" in settings_page.text
    token = page_csrf(settings_page)

    # Wrong current password is rejected.
    response = client.post(
        "/settings/credentials",
        data={
            "current_password": "wrong",
            "new_password": "newsecret123",
            "confirm_password": "newsecret123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "wrong_current_password" in response.headers["location"]
    assert main.valid_login("admin", "secret")

    # Successful change: new password works, old one is rejected, session survives.
    response = client.post(
        "/settings/credentials",
        data={
            "current_password": "secret",
            "new_password": "newsecret123",
            "confirm_password": "newsecret123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "credentials_updated" in response.headers["location"]
    assert database.get_user_password_hash("admin") != os.environ["APP_PASSWORD_HASH"]
    assert main.valid_login("admin", "newsecret123")
    assert not main.valid_login("admin", "secret")
    assert client.get("/").status_code == 200  # re-signed session cookie still valid

    # Username change moves the credential row.
    token = page_csrf(client.get("/settings"))
    response = client.post(
        "/settings/credentials",
        data={
            "current_password": "newsecret123",
            "new_username": "sarthak",
            "new_password": "newsecret123",
            "confirm_password": "newsecret123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert main.valid_login("sarthak", "newsecret123")
    assert database.get_user_password_hash("admin") is None

    # Validation: short password and mismatch are rejected.
    token = page_csrf(client.get("/settings"))
    response = client.post(
        "/settings/credentials",
        data={
            "current_password": "newsecret123",
            "new_password": "short",
            "confirm_password": "short",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert "weak_password" in response.headers["location"]
    response = client.post(
        "/settings/credentials",
        data={
            "current_password": "newsecret123",
            "new_password": "newsecret456",
            "confirm_password": "different789",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert "password_mismatch" in response.headers["location"]


def test_login_lockout_after_repeated_failures(tmp_path):
    client = client_with_db(tmp_path)
    main.login_failures.clear()
    try:
        token = csrf_from_login_page(client)
        for _ in range(main.LOGIN_LOCKOUT_THRESHOLD):
            response = client.post(
                "/login",
                data={"username": "admin", "password": "nope", "csrf_token": token},
                follow_redirects=False,
            )
            assert response.status_code == 200
            assert "Invalid username or password." in response.text

        # Correct credentials are refused while the lockout is active.
        response = client.post(
            "/login",
            data={"username": "admin", "password": "secret", "csrf_token": token},
            follow_redirects=False,
        )
        assert response.status_code == 429
        assert "Too many failed attempts" in response.text
    finally:
        main.login_failures.clear()


def test_security_headers_present(tmp_path):
    client = client_with_db(tmp_path)
    response = client.get("/login")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "noindex" in response.headers["X-Robots-Tag"]


def test_multi_user_data_isolation(tmp_path):
    client = client_with_db(tmp_path)
    login(client)

    page = client.get("/settings")
    assert "User accounts" in page.text
    token = page_csrf(page)
    response = client.post(
        "/admin/users/add",
        data={
            "username": "priya",
            "password": "priyapass123",
            "confirm_password": "priyapass123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "user_created" in response.headers["location"]
    priya_id = database.get_user_by_username("priya")["id"]

    # Duplicate username is rejected.
    token = page_csrf(client.get("/settings"))
    response = client.post(
        "/admin/users/add",
        data={
            "username": "priya",
            "password": "whatever123",
            "confirm_password": "whatever123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert "username_taken" in response.headers["location"]

    # The second user logs in on their own client and sees an empty ledger.
    client2 = TestClient(main.app)
    token = csrf_from_login_page(client2)
    response = client2.post(
        "/login",
        data={"username": "priya", "password": "priyapass123", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert database.list_expenses(priya_id) == []

    admin_expense = add_sample_expense(client, category="Food")

    token = page_csrf(client2.get("/"))
    response = client2.post(
        "/add",
        data={
            "amount": "300.00",
            "category": "Travel",
            "description": "Priya cab",
            "transaction_type": "expense",
            "status": "completed",
            "transaction_date": "2026-06-12T10:00",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    # Each ledger only contains its owner's rows.
    assert [e["id"] for e in database.list_expenses(admin_id())] == [admin_expense["id"]]
    assert [e["description"] for e in database.list_expenses(priya_id)] == ["Priya cab"]
    assert "Lunch" not in client2.get("/").text
    assert "Priya cab" not in client.get("/").text

    # Budgets are private too.
    token = page_csrf(client2.get("/budgets"))
    response = client2.post(
        "/budgets/set",
        data={"category": "Travel", "monthly_limit": "4000", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert database.get_budgets(priya_id)["Travel"] == 4000.0
    assert database.get_budgets(admin_id())["Travel"] == 9000.0  # default untouched


def test_admin_user_management_guards(tmp_path):
    client = client_with_db(tmp_path)
    login(client)

    page = client.get("/settings")
    token = page_csrf(page)
    client.post(
        "/admin/users/add",
        data={
            "username": "temp",
            "password": "temppass123",
            "confirm_password": "temppass123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    temp_id = database.get_user_by_username("temp")["id"]

    # Admin can reset a user's password; the new one works, the old one does not.
    token = page_csrf(client.get("/settings"))
    response = client.post(
        f"/admin/users/reset-password/{temp_id}",
        data={
            "new_password": "freshpass123",
            "confirm_password": "freshpass123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert "password_reset" in response.headers["location"]
    assert not main.valid_login("temp", "temppass123")
    assert main.valid_login("temp", "freshpass123")

    # Admin cannot delete their own account.
    own_id = admin_id()
    token = page_csrf(client.get("/settings"))
    response = client.post(
        f"/admin/users/delete/{own_id}",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert "last_admin" in response.headers["location"]
    assert database.get_user_by_id(own_id) is not None

    # Deleting the user removes all of their data.
    add_sample_expense(client, category="Food")
    temp_client = TestClient(main.app)
    token = csrf_from_login_page(temp_client)
    temp_client.post(
        "/login",
        data={"username": "temp", "password": "freshpass123", "csrf_token": token},
        follow_redirects=False,
    )
    token = page_csrf(temp_client.get("/"))
    temp_client.post(
        "/add",
        data={
            "amount": "50",
            "category": "Food",
            "description": "temp snack",
            "transaction_type": "expense",
            "status": "completed",
            "transaction_date": "2026-06-10T10:00",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert len(database.list_expenses(temp_id)) == 1

    token = page_csrf(client.get("/settings"))
    response = client.post(
        f"/admin/users/delete/{temp_id}",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert "user_deleted" in response.headers["location"]
    assert database.get_user_by_id(temp_id) is None
    assert database.list_expenses(temp_id) == []


def test_register_creates_first_admin_then_closes(tmp_path):
    saved_username = os.environ.pop("APP_USERNAME", None)
    saved_hash = os.environ.pop("APP_PASSWORD_HASH", None)
    try:
        client = client_with_db(tmp_path)
        assert database.count_users() == 0

        page = client.get("/register")
        assert page.status_code == 200
        token = page_csrf(page)
        response = client.post(
            "/register",
            data={
                "username": "owner",
                "password": "bootpass123",
                "confirm_password": "bootpass123",
                "csrf_token": token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        admin = database.get_user_by_username("owner")
        assert admin is not None and admin["is_admin"] == 1
        assert client.get("/").status_code == 200  # session established
        assert (
            client.get("/register", follow_redirects=False).status_code == 302
        )  # registration closed
        assert "Create the owner account" not in client.get("/login").text

        # Default budgets were provisioned for the new owner.
        assert database.get_budgets(admin["id"]) != {}
    finally:
        if saved_username is not None:
            os.environ["APP_USERNAME"] = saved_username
        if saved_hash is not None:
            os.environ["APP_PASSWORD_HASH"] = saved_hash


def test_legacy_single_user_data_migrates(tmp_path):
    amount_type = "DOUBLE PRECISION" if database.database_url() else "REAL"
    legacy_sql = """
        DROP TABLE IF EXISTS expenses;
        DROP TABLE IF EXISTS budgets;
        DROP TABLE IF EXISTS app_users;
        CREATE TABLE expenses (
            id TEXT PRIMARY KEY,
            amount {amount} NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL CHECK(category != ''),
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        INSERT INTO expenses (id, amount, category, description, created_at)
            VALUES ('legacy-1', 250.0, 'Food', 'Old lunch', '2026-05-01 12:00:00');
        CREATE TABLE budgets (
            category TEXT PRIMARY KEY,
            monthly_limit {amount} NOT NULL CHECK(monthly_limit > 0)
        );
        INSERT INTO budgets (category, monthly_limit) VALUES ('Food', 9000.0);
        CREATE TABLE app_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO app_users (username, password_hash, updated_at)
            VALUES ('olduser', 'legacyhash', '2026-05-01 00:00:00');
    """.replace("{amount}", amount_type)

    if database.database_url():
        # Rebuild the legacy schema inside the shared test database.
        with database.get_connection() as conn:
            for statement in legacy_sql.split(";"):
                if statement.strip():
                    conn.execute(statement)
    else:
        database.DATABASE_FILE = tmp_path / "legacy.db"
        database.CSV_FILE = tmp_path / "missing.csv"
        conn = sqlite3.connect(database.DATABASE_FILE)
        conn.executescript(legacy_sql)
        conn.commit()
        conn.close()

    database.init_db()

    owner = database.get_user_by_username("olduser")
    assert owner is not None and owner["is_admin"] == 1

    expenses = database.list_expenses(owner["id"])
    assert len(expenses) == 1
    assert expenses[0]["id"] == "legacy-1"
    assert expenses[0]["transaction_type"] == "expense"

    budgets = database.get_budgets(owner["id"])
    assert budgets == {"Food": 9000.0}  # legacy limit kept, defaults not duplicated
