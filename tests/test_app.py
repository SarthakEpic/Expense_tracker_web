import os
import re
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("APP_USERNAME", "admin")
os.environ.setdefault("APP_PASSWORD_HASH", "pbkdf2_sha256$120000$testsalt$0")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.append(str(Path(__file__).resolve().parents[1]))

import database
import main
from fastapi.testclient import TestClient


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
    return database.list_expenses()[0]


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
    assert database.get_expense(expense["id"])["category"] == "Travel"

    home = client.get("/")
    token = page_csrf(home)
    response = client.post(
        f"/delete/{expense['id']}",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert database.list_expenses() == []


def test_csrf_blocks_mutating_request(tmp_path):
    client = client_with_db(tmp_path)
    login(client)
    response = client.post(
        "/add",
        data={"amount": "12", "category": "Food", "description": "Missing token"},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert database.list_expenses() == []


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
