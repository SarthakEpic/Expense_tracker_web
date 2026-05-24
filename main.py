import csv
import hashlib
import hmac
import os
from contextlib import asynccontextmanager
from datetime import datetime
from io import StringIO
from secrets import compare_digest, token_urlsafe

import matplotlib
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

import database


matplotlib.use("Agg")
import matplotlib.pyplot as plt


load_dotenv()

USERNAME = os.getenv("APP_USERNAME")
PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH")
LEGACY_PASSWORD = os.getenv("APP_PASSWORD")
SECRET_KEY = os.getenv("SECRET_KEY")
CSRF_COOKIE = "csrf_token"
SESSION_COOKIE = "session_token"

if not USERNAME or not SECRET_KEY:
    raise RuntimeError("APP_USERNAME and SECRET_KEY must be set in .env")

@asynccontextmanager
async def lifespan(app):
    database.migrate_csv_to_sqlite()
    yield


serializer = URLSafeSerializer(SECRET_KEY)
app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"pbkdf2_sha256$120000${salt}${digest}"


def verify_password(password, password_hash):
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return compare_digest(digest, expected)


def valid_login(username, password):
    if username != USERNAME:
        return False
    if PASSWORD_HASH:
        return verify_password(password, PASSWORD_HASH)
    return bool(LEGACY_PASSWORD and hmac.compare_digest(password, LEGACY_PASSWORD))


def get_session_user(request):
    session_cookie = request.cookies.get(SESSION_COOKIE)
    if not session_cookie:
        return None
    try:
        user = serializer.loads(session_cookie)
    except BadSignature:
        return None
    return user if user == USERNAME else None


def require_login(request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return user


def get_csrf_token(request):
    token = request.cookies.get(CSRF_COOKIE)
    return token or token_urlsafe(32)


def attach_csrf_cookie(response, token):
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
    )


def validate_csrf(request, csrf_token):
    cookie_token = request.cookies.get(CSRF_COOKIE)
    return bool(cookie_token and csrf_token and compare_digest(cookie_token, csrf_token))


def redirect_with_message(message):
    return RedirectResponse(url=f"/?msg={message}", status_code=302)


def get_messages(key):
    messages = {
        "added": "Expense added successfully.",
        "deleted": "Expense deleted.",
        "edited": "Expense updated.",
        "invalid_amount": "Amount must be greater than zero.",
        "invalid_csrf": "Please try again. The form token expired.",
    }
    return messages.get(key, "")


def get_monthly_totals(year=None):
    return database.monthly_totals(year=year)


def generate_monthly_chart(monthly_totals):
    chart_path = os.path.join("static", "monthly_chart.png")

    plt.figure(figsize=(8, 4))
    if monthly_totals:
        months = [month for month, _ in monthly_totals]
        totals = [total for _, total in monthly_totals]
        plt.bar(months, totals, color="#2e86de")
        plt.xlabel("Month")
        plt.ylabel("Total Spending")
        plt.title("Monthly Spending")
        plt.xticks(rotation=45)
    else:
        plt.text(0.5, 0.5, "No expenses yet", ha="center", va="center", fontsize=14)
        plt.axis("off")

    plt.tight_layout()
    plt.savefig(chart_path)
    plt.close()
    return "/static/monthly_chart.png"


def unique_periods(expenses):
    years = sorted({expense["date"][:4] for expense in expenses}, reverse=True)
    months = sorted({expense["date"][:7] for expense in expenses}, reverse=True)
    return years, months


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = get_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"error": "", "csrf_token": token},
    )
    attach_csrf_cookie(response, token)
    return response


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse(url="/login", status_code=302)

    if valid_login(username, password):
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=serializer.dumps(username),
            httponly=True,
            samesite="lax",
        )
        return response

    token = get_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": "Invalid username or password.",
            "csrf_token": token,
        },
    )
    attach_csrf_cookie(response, token)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    category: str = "",
    month: str = "",
    year: str = "",
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    all_expenses = database.list_expenses()
    expenses = database.list_expenses(
        category=category or None,
        month=month or None,
        year=year or None,
    )
    total_spent = sum(expense["amount"] for expense in expenses)
    monthly_totals = get_monthly_totals(year=year or None)
    yearly_totals = database.yearly_totals()
    category_totals = database.category_totals()
    chart_url = generate_monthly_chart(monthly_totals) + f"?v={datetime.now().timestamp()}"
    years, months = unique_periods(all_expenses)
    token = get_csrf_token(request)

    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "message": get_messages(request.query_params.get("msg")),
            "expenses": expenses,
            "categories": database.list_categories(),
            "selected_category": category,
            "selected_month": month,
            "selected_year": year,
            "months": months,
            "years": years,
            "monthly_totals": monthly_totals,
            "yearly_totals": yearly_totals,
            "category_totals": category_totals,
            "chart_url": chart_url,
            "total_spent": total_spent,
            "csrf_token": token,
        },
    )
    attach_csrf_cookie(response, token)
    return response


@app.post("/add")
async def add_expense(
    request: Request,
    amount: float = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    csrf_token: str = Form(...),
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return redirect_with_message("invalid_csrf")
    if amount <= 0:
        return redirect_with_message("invalid_amount")

    database.add_expense(amount, category, description)
    return redirect_with_message("added")


@app.post("/delete/{expense_id}")
async def delete_expense(request: Request, expense_id: str, csrf_token: str = Form(...)):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return redirect_with_message("invalid_csrf")

    database.delete_expense(expense_id)
    return redirect_with_message("deleted")


@app.get("/edit/{expense_id}", response_class=HTMLResponse)
async def edit_expense_form(request: Request, expense_id: str):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    expense = database.get_expense(expense_id)
    if not expense:
        return RedirectResponse(url="/", status_code=302)

    token = get_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "edit.html",
        {
            "expense_id": expense_id,
            "amount": f'{expense["amount"]:.2f}',
            "category": expense["category"],
            "description": expense["description"],
            "categories": database.list_categories(),
            "csrf_token": token,
        },
    )
    attach_csrf_cookie(response, token)
    return response


@app.post("/edit/{expense_id}")
async def save_edited_expense(
    request: Request,
    expense_id: str,
    amount: float = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    csrf_token: str = Form(...),
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return redirect_with_message("invalid_csrf")
    if amount <= 0:
        return RedirectResponse(url=f"/edit/{expense_id}", status_code=302)

    database.update_expense(expense_id, amount, category, description)
    return redirect_with_message("edited")


@app.get("/export")
async def export_expenses(
    request: Request,
    category: str = "",
    month: str = "",
    year: str = "",
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    expenses = database.list_expenses(
        category=category or None,
        month=month or None,
        year=year or None,
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["amount", "category", "description", "date"])
    for expense in expenses:
        writer.writerow(
            [
                f'{expense["amount"]:.2f}',
                expense["category"],
                expense["description"],
                expense["date"],
            ]
        )

    filename = f"expenses-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(output.getvalue(), media_type="text/csv", headers=headers)
