import os
import re
import sys
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


def add_sample_expense(client, category="Food"):
    response = client.get("/")
    token = page_csrf(response)
    response = client.post(
        "/add",
        data={
            "amount": "120.50",
            "category": category,
            "description": "Lunch",
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
    assert "Food" in response.text
    assert "120.50" in response.text

    edit_page = client.get(f"/edit/{expense['id']}")
    token = page_csrf(edit_page)
    response = client.post(
        f"/edit/{expense['id']}",
        data={
            "amount": "99.99",
            "category": "Travel",
            "description": "Cab",
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
    assert "Visible Expenses" in response.text
    assert "<strong>1</strong>" in response.text

    export = client.get("/export?category=Food")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "Food" in export.text
    assert "Bills" not in export.text
