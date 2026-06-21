import csv
import hashlib
import hmac
import os
from calendar import monthrange
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from io import StringIO
from math import isfinite
from secrets import compare_digest, token_urlsafe

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

import database


load_dotenv()

USERNAME = os.getenv("APP_USERNAME")
PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH")
LEGACY_PASSWORD = os.getenv("APP_PASSWORD")
SECRET_KEY = os.getenv("SECRET_KEY")
CSRF_COOKIE = "csrf_token"
SESSION_COOKIE = "session_token"
TRANSACTION_TYPES = {"expense", "income"}
TRANSACTION_STATUSES = {"completed", "pending"}
PAGE_SIZE = 10
BUDGET_LIMITS = {
    "Food": 12000,
    "Travel": 9000,
    "Shopping": 15000,
    "Bills": 18000,
}
CHART_COLORS = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]
COMING_SOON_FEATURES = [
    {
        "title": "AI Spending Assistant",
        "copy": "Weekly nudges that explain where your cash flow changed and what to do next.",
        "status": "Coming soon",
    },
    {
        "title": "Receipt OCR Scanner",
        "copy": "Snap receipts, auto-fill merchants and categories, then review before posting.",
        "status": "Coming soon",
    },
    {
        "title": "Recurring Transactions",
        "copy": "Track subscriptions, rent, and salaries without creating the same entries every month.",
        "status": "Coming soon",
    },
    {
        "title": "Smart Savings Goals",
        "copy": "Tie target goals to your real balance and pace them against recent habits.",
        "status": "Coming soon",
    },
    {
        "title": "Spending Prediction",
        "copy": "Forecast month-end burn based on current pacing, recurring charges, and pending items.",
        "status": "Coming soon",
    },
]

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


def redirect_with_message(message, target="/"):
    return RedirectResponse(url=f"{target}?msg={message}", status_code=302)


def get_messages(key):
    messages = {
        "added": "Transaction added successfully.",
        "deleted": "Transaction deleted.",
        "edited": "Transaction updated.",
        "invalid_amount": "Amount must be greater than zero.",
        "invalid_transaction": "Choose a valid transaction type, status, and date.",
        "invalid_csrf": "Please try again. The form token expired.",
        "budget_draft": "Budget creation is staged as a future workflow in this prototype.",
        "export_mock": "CSV is live. Excel and PDF exports are staged as premium report actions.",
    }
    return messages.get(key, "")


def display_name(username):
    return username.split("@")[0].replace("_", " ").replace("-", " ").title()


def unique_periods(expenses):
    years = sorted({expense["date"][:4] for expense in expenses}, reverse=True)
    months = sorted({expense["date"][:7] for expense in expenses}, reverse=True)
    return years, months


def parse_transaction_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime(database.DATE_FORMAT)
        except ValueError:
            continue
    return None


def datetime_local_value(value):
    return datetime.strptime(value, database.DATE_FORMAT).strftime("%Y-%m-%dT%H:%M")


def percent_change(current, previous):
    if previous == 0:
        return 100.0 if current else 0.0
    return ((current - previous) / previous) * 100


def format_period(period):
    return datetime.strptime(period, "%Y-%m").strftime("%b")


def build_sparkline(values, width=320, height=120, padding=14):
    if not values:
        return ""
    if len(values) == 1:
        y = height / 2
        return f"{padding},{y:.1f} {width - padding},{y:.1f}"

    max_value = max(values)
    min_value = min(values)
    spread = max(max_value - min_value, 1)
    step = (width - padding * 2) / (len(values) - 1)
    points = []
    for index, value in enumerate(values):
        x = padding + index * step
        y = height - padding - ((value - min_value) / spread) * (height - padding * 2)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def build_budget_rows(transactions, now):
    current_period = now.strftime("%Y-%m")
    spend_by_category = defaultdict(float)
    for transaction in transactions:
        if (
            transaction["status"] == "completed"
            and transaction["transaction_type"] == "expense"
            and transaction["date"].startswith(current_period)
        ):
            spend_by_category[transaction["category"]] += transaction["amount"]

    rows = []
    for category, limit in BUDGET_LIMITS.items():
        spent = spend_by_category.get(category, 0.0)
        usage = spent / limit * 100 if limit else 0
        status = "Safe"
        if usage > 100:
            status = "Over Budget"
        elif usage >= 80:
            status = "Warning"
        rows.append(
            {
                "category": category,
                "spent": spent,
                "limit": limit,
                "usage": min(usage, 100),
                "actual_usage": usage,
                "remaining": max(limit - spent, 0),
                "status": status,
            }
        )
    return rows


def build_insights(category_totals, budgets, expenses):
    insights = []
    if category_totals:
        top_category, top_amount = category_totals[0]
        insights.append(
            {
                "title": "Top category",
                "copy": f"{top_category} leads your completed spending at INR {top_amount:.0f}.",
            }
        )
    if expenses:
        largest = max(
            (
                transaction
                for transaction in expenses
                if transaction["transaction_type"] == "expense"
            ),
            key=lambda item: item["amount"],
            default=None,
        )
        if largest:
            insights.append(
                {
                    "title": "Largest expense",
                    "copy": f"{largest.get('description') or largest['category']} for INR {largest['amount']:.0f}.",
                }
            )
    warning_budget = next((budget for budget in budgets if budget["actual_usage"] >= 80), None)
    if warning_budget:
        insights.append(
            {
                "title": "Budget watch",
                "copy": f"{warning_budget['category']} is at {warning_budget['actual_usage']:.0f}% of its monthly limit.",
            }
        )
    if not insights:
        insights.append(
            {
                "title": "Waiting for activity",
                "copy": "Add a few transactions and the dashboard will start surfacing trends and watch points.",
            }
        )
    return insights[:3]


def summarize_expenses(transactions, now=None):
    now = now or datetime.now()
    completed = [item for item in transactions if item["status"] == "completed"]
    completed_expenses = [item for item in completed if item["transaction_type"] == "expense"]
    completed_income = [item for item in completed if item["transaction_type"] == "income"]

    monthly_expenses = defaultdict(float)
    monthly_income = defaultdict(float)
    categories = defaultdict(float)
    for transaction in completed_expenses:
        period = transaction["date"][:7]
        monthly_expenses[period] += transaction["amount"]
        categories[transaction["category"]] += transaction["amount"]
    for transaction in completed_income:
        monthly_income[transaction["date"][:7]] += transaction["amount"]

    periods = sorted(set(monthly_expenses) | set(monthly_income))
    monthly_timeline = [
        {
            "period": period,
            "label": format_period(period),
            "income": monthly_income.get(period, 0.0),
            "expenses": monthly_expenses.get(period, 0.0),
            "savings": monthly_income.get(period, 0.0) - monthly_expenses.get(period, 0.0),
        }
        for period in periods
    ]
    timeline_window = monthly_timeline[-6:]

    category_totals = sorted(categories.items(), key=lambda item: item[1], reverse=True)
    visible_categories = category_totals[:4]
    if len(category_totals) > 4:
        visible_categories.append(("Other", sum(total for _, total in category_totals[4:])))

    total_category_spend = sum(total for _, total in visible_categories)
    gradient_stops = []
    position = 0.0
    for index, (_, total) in enumerate(visible_categories):
        next_position = position + (total / total_category_spend * 100 if total_category_spend else 0)
        color = CHART_COLORS[index]
        gradient_stops.append(f"{color} {position:.2f}% {next_position:.2f}%")
        position = next_position

    current_period = now.strftime("%Y-%m")
    previous_period = (
        datetime(now.year - 1, 12, 1).strftime("%Y-%m")
        if now.month == 1
        else datetime(now.year, now.month - 1, 1).strftime("%Y-%m")
    )
    current_expense_total = monthly_expenses.get(current_period, 0.0)
    current_income_total = monthly_income.get(current_period, 0.0)
    previous_expense_total = monthly_expenses.get(previous_period, 0.0)
    previous_income_total = monthly_income.get(previous_period, 0.0)

    days_in_month = monthrange(now.year, now.month)[1]
    projected_total = current_expense_total / now.day * days_in_month if current_expense_total else 0.0
    projected_additional = max(projected_total - current_expense_total, 0.0)

    monthly_spending = []
    for item in timeline_window:
        projection = projected_additional if item["period"] == current_period else 0.0
        monthly_spending.append(
            {
                "period": item["period"],
                "label": item["label"],
                "actual": item["expenses"],
                "projection": projection,
            }
        )

    max_monthly_total = max(
        (item["actual"] + item["projection"] for item in monthly_spending),
        default=0.0,
    )
    cashflow_monthly = [
        {
            "period": item["period"],
            "label": item["label"],
            "income": item["income"],
            "expenses": item["expenses"],
            "net": item["savings"],
            "net_abs": abs(item["savings"]),
        }
        for item in timeline_window
    ]
    max_cashflow = max(
        (max(item["income"], item["expenses"]) for item in cashflow_monthly),
        default=0.0,
    )

    budgets = build_budget_rows(transactions, now)
    total_income = sum(item["amount"] for item in completed_income)
    total_spent = sum(item["amount"] for item in completed_expenses)
    total_savings = total_income - total_spent
    total_budget_limit = sum(item["limit"] for item in budgets)
    current_budget_spent = sum(item["spent"] for item in budgets)
    current_budget_usage = (
        current_budget_spent / total_budget_limit * 100 if total_budget_limit else 0.0
    )
    previous_budget_spent = previous_expense_total
    previous_budget_usage = (
        previous_budget_spent / total_budget_limit * 100 if total_budget_limit else 0.0
    )

    spending_values = [item["expenses"] for item in timeline_window] or [0]
    income_values = [item["income"] for item in timeline_window] or [0]
    savings_values = [item["savings"] for item in timeline_window] or [0]

    return {
        "monthly_spending": monthly_spending,
        "cashflow_monthly": cashflow_monthly,
        "category_totals": visible_categories,
        "max_monthly_total": max_monthly_total,
        "max_cashflow": max_cashflow,
        "donut_gradient": ", ".join(gradient_stops) if gradient_stops else "#e2e8f0 0 100%",
        "total_spent": total_spent,
        "total_income": total_income,
        "total_savings": total_savings,
        "average_expense": total_spent / len(completed_expenses) if completed_expenses else 0.0,
        "projected_spending": projected_total,
        "pending_total": sum(
            item["amount"] for item in transactions if item["status"] == "pending"
        ),
        "pending_count": sum(1 for item in transactions if item["status"] == "pending"),
        "current_period_label": now.strftime("%B %Y"),
        "expense_change": percent_change(current_expense_total, previous_expense_total),
        "income_change": percent_change(current_income_total, previous_income_total),
        "savings_change": percent_change(
            current_income_total - current_expense_total,
            previous_income_total - previous_expense_total,
        ),
        "budget_usage": current_budget_usage,
        "budget_usage_change": current_budget_usage - previous_budget_usage,
        "budget_rows": budgets,
        "insights": build_insights(category_totals, budgets, completed_expenses),
        "timeline_window": timeline_window,
        "spending_points": build_sparkline(spending_values),
        "income_points": build_sparkline(income_values),
        "savings_points": build_sparkline(savings_values),
        "spending_max": max(spending_values) if spending_values else 0.0,
        "income_max": max(income_values) if income_values else 0.0,
        "savings_max": max(abs(value) for value in savings_values) if savings_values else 0.0,
    }


def get_navigation(active_page):
    items = [
        ("dashboard", "Dashboard", "/"),
        ("transactions", "Transactions", "/transactions"),
        ("analytics", "Analytics", "/analytics"),
        ("budgets", "Budgets", "/budgets"),
        ("reports", "Reports", "/reports"),
        ("settings", "Settings", "/settings"),
        ("coming-soon", "Coming Soon", "/coming-soon"),
    ]
    return [
        {"key": key, "label": label, "href": href, "active": key == active_page}
        for key, label, href in items
    ]


def page_meta(page, user_name):
    meta = {
        "dashboard": {
            "eyebrow": "Financial overview",
            "title": "Good Evening",
            "subtitle": f"Welcome back {user_name}. Here is your financial overview.",
        },
        "transactions": {
            "eyebrow": "Transaction ledger",
            "title": "Transactions",
            "subtitle": "Search, sort, and review every inflow and outflow from one clean table.",
        },
        "analytics": {
            "eyebrow": "Trend analysis",
            "title": "Analytics",
            "subtitle": "Follow monthly movement across spending, income, savings, and category concentration.",
        },
        "budgets": {
            "eyebrow": "Monthly controls",
            "title": "Budgets",
            "subtitle": "See which categories are safe, which are stretching, and where overspending is starting.",
        },
        "reports": {
            "eyebrow": "Reporting hub",
            "title": "Reports",
            "subtitle": "Export the current data, review monthly rollups, and stage richer reporting workflows.",
        },
        "settings": {
            "eyebrow": "Workspace preferences",
            "title": "Settings",
            "subtitle": "Theme, notifications, and profile preferences for the current prototype.",
        },
        "coming-soon": {
            "eyebrow": "Product roadmap",
            "title": "Coming Soon",
            "subtitle": "Future concepts are kept visible here instead of being mixed into live financial data.",
        },
    }
    return meta[page]


def build_shared_context(request, active_page, expenses, selected_expenses=None):
    session_user = get_session_user(request)
    if not session_user:
        return None

    token = get_csrf_token(request)
    user_name = display_name(session_user)
    selected_expenses = selected_expenses if selected_expenses is not None else expenses
    years, months = unique_periods(expenses)
    summary = summarize_expenses(selected_expenses)
    now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")

    return {
        "message": get_messages(request.query_params.get("msg")),
        "csrf_token": token,
        "user_name": user_name,
        "user_email": f"{session_user}@example.com" if "@" not in session_user else session_user,
        "user_initial": user_name[:1].upper(),
        "categories": sorted(set(database.list_categories()) | set(BUDGET_LIMITS)),
        "months": months,
        "years": years,
        "nav_items": get_navigation(active_page),
        "page_meta": page_meta(active_page, user_name),
        "active_page": active_page,
        "default_transaction_date": now_value,
        "coming_soon_features": COMING_SOON_FEATURES,
        "balance": summary["total_income"] - summary["total_spent"],
        "balance_abs": abs(summary["total_income"] - summary["total_spent"]),
        **summary,
    }


def render_page(request, template_name, context):
    response = templates.TemplateResponse(request, template_name, context)
    attach_csrf_cookie(response, context["csrf_token"])
    return response


def parse_transaction_sort(transactions, sort):
    sort_key = sort or "newest"
    if sort_key == "oldest":
        return sorted(transactions, key=lambda item: item["date"])
    if sort_key == "amount_high":
        return sorted(transactions, key=lambda item: item["amount"], reverse=True)
    if sort_key == "amount_low":
        return sorted(transactions, key=lambda item: item["amount"])
    if sort_key == "category":
        return sorted(transactions, key=lambda item: (item["category"], item["date"]), reverse=False)
    return sorted(transactions, key=lambda item: item["date"], reverse=True)


def filter_transactions(transactions, search="", category="", transaction_type="", status="", date_from="", date_to=""):
    filtered = transactions
    if search:
        query = search.lower().strip()
        filtered = [
            item
            for item in filtered
            if query in item["category"].lower() or query in (item["description"] or "").lower()
        ]
    if category:
        filtered = [item for item in filtered if item["category"] == category]
    if transaction_type:
        filtered = [item for item in filtered if item["transaction_type"] == transaction_type]
    if status:
        filtered = [item for item in filtered if item["status"] == status]
    if date_from:
        filtered = [item for item in filtered if item["date"][:10] >= date_from]
    if date_to:
        filtered = [item for item in filtered if item["date"][:10] <= date_to]
    return filtered


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
    transaction_type: str = "",
    status: str = "",
):
    all_expenses = database.list_expenses()
    selected_expenses = database.list_expenses(
        category=category or None,
        month=month or None,
        year=year or None,
        transaction_type=transaction_type or None,
        status=status or None,
    )
    context = build_shared_context(request, "dashboard", all_expenses, selected_expenses)
    if not context:
        return RedirectResponse(url="/login", status_code=302)

    context.update(
        {
            "selected_category": category,
            "selected_month": month,
            "selected_year": year,
            "selected_type": transaction_type,
            "selected_status": status,
            "recent_transactions": selected_expenses[:5],
            "dashboard_total_transactions": len(selected_expenses),
        }
    )
    return render_page(request, "dashboard.html", context)


@app.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    search: str = "",
    category: str = "",
    transaction_type: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "newest",
    page: int = 1,
):
    all_expenses = database.list_expenses()
    filtered = filter_transactions(
        all_expenses,
        search=search,
        category=category,
        transaction_type=transaction_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    ordered = parse_transaction_sort(filtered, sort)
    page = max(page, 1)
    page_count = max((len(ordered) + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, page_count)
    start = (page - 1) * PAGE_SIZE
    page_items = ordered[start : start + PAGE_SIZE]

    context = build_shared_context(request, "transactions", all_expenses, filtered)
    if not context:
        return RedirectResponse(url="/login", status_code=302)

    context.update(
        {
            "expenses": page_items,
            "search": search,
            "selected_category": category,
            "selected_type": transaction_type,
            "selected_status": status,
            "selected_date_from": date_from,
            "selected_date_to": date_to,
            "selected_sort": sort,
            "page_number": page,
            "page_count": page_count,
            "total_transactions": len(ordered),
        }
    )
    return render_page(request, "transactions.html", context)


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    all_expenses = database.list_expenses()
    context = build_shared_context(request, "analytics", all_expenses)
    if not context:
        return RedirectResponse(url="/login", status_code=302)
    return render_page(request, "analytics.html", context)


@app.get("/budgets", response_class=HTMLResponse)
async def budgets_page(request: Request):
    all_expenses = database.list_expenses()
    context = build_shared_context(request, "budgets", all_expenses)
    if not context:
        return RedirectResponse(url="/login", status_code=302)
    return render_page(request, "budgets.html", context)


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    all_expenses = database.list_expenses()
    context = build_shared_context(request, "reports", all_expenses)
    if not context:
        return RedirectResponse(url="/login", status_code=302)

    quarter_total = sum(item["income"] - item["expenses"] for item in context["timeline_window"][-3:])
    year_total = sum(item["income"] - item["expenses"] for item in context["timeline_window"][-12:])
    context.update(
        {
            "monthly_report_total": context["balance"],
            "monthly_report_total_abs": abs(context["balance"]),
            "quarterly_report_total": quarter_total,
            "quarterly_report_total_abs": abs(quarter_total),
            "yearly_report_total": year_total,
            "yearly_report_total_abs": abs(year_total),
        }
    )
    return render_page(request, "reports.html", context)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    all_expenses = database.list_expenses()
    context = build_shared_context(request, "settings", all_expenses)
    if not context:
        return RedirectResponse(url="/login", status_code=302)
    return render_page(request, "settings.html", context)


@app.get("/coming-soon", response_class=HTMLResponse)
async def coming_soon_page(request: Request):
    all_expenses = database.list_expenses()
    context = build_shared_context(request, "coming-soon", all_expenses)
    if not context:
        return RedirectResponse(url="/login", status_code=302)
    return render_page(request, "coming-soon.html", context)


@app.post("/add")
async def add_expense(
    request: Request,
    amount: float = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    transaction_type: str = Form("expense"),
    status: str = Form("completed"),
    transaction_date: str = Form(""),
    csrf_token: str = Form(...),
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return redirect_with_message("invalid_csrf")
    if not isfinite(amount) or amount <= 0:
        return redirect_with_message("invalid_amount")
    created_at = parse_transaction_datetime(transaction_date)
    if (
        transaction_type not in TRANSACTION_TYPES
        or status not in TRANSACTION_STATUSES
        or not created_at
    ):
        return redirect_with_message("invalid_transaction")

    database.add_expense(
        amount,
        category,
        description,
        transaction_type,
        status,
        created_at=created_at,
    )
    target = request.headers.get("referer") or "/"
    return RedirectResponse(url=target, status_code=302)


@app.post("/delete/{expense_id}")
async def delete_expense(request: Request, expense_id: str, csrf_token: str = Form(...)):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return redirect_with_message("invalid_csrf")

    database.delete_expense(expense_id)
    target = request.headers.get("referer") or "/transactions"
    return RedirectResponse(url=target, status_code=302)


@app.get("/edit/{expense_id}", response_class=HTMLResponse)
async def edit_expense_form(request: Request, expense_id: str):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    expense = database.get_expense(expense_id)
    if not expense:
        return RedirectResponse(url="/transactions", status_code=302)

    token = get_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "edit.html",
        {
            "expense_id": expense_id,
            "amount": f'{expense["amount"]:.2f}',
            "category": expense["category"],
            "description": expense["description"],
            "transaction_type": expense["transaction_type"],
            "status": expense["status"],
            "transaction_date": datetime_local_value(expense["created_at"]),
            "categories": sorted(set(database.list_categories()) | set(BUDGET_LIMITS)),
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
    transaction_type: str = Form("expense"),
    status: str = Form("completed"),
    transaction_date: str = Form(""),
    csrf_token: str = Form(...),
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return redirect_with_message("invalid_csrf")
    if not isfinite(amount) or amount <= 0:
        return RedirectResponse(url=f"/edit/{expense_id}", status_code=302)
    created_at = parse_transaction_datetime(transaction_date)
    if (
        transaction_type not in TRANSACTION_TYPES
        or status not in TRANSACTION_STATUSES
        or not created_at
    ):
        return RedirectResponse(url=f"/edit/{expense_id}", status_code=302)

    database.update_expense(
        expense_id,
        amount,
        category,
        description,
        transaction_type,
        status,
        created_at=created_at,
    )
    return redirect_with_message("edited", "/transactions")


@app.get("/export")
async def export_expenses(
    request: Request,
    category: str = "",
    month: str = "",
    year: str = "",
    transaction_type: str = "",
    status: str = "",
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    expenses = database.list_expenses(
        category=category or None,
        month=month or None,
        year=year or None,
        transaction_type=transaction_type or None,
        status=status or None,
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["type", "status", "amount", "category", "description", "date"])
    for expense in expenses:
        writer.writerow(
            [
                expense["transaction_type"],
                expense["status"],
                f'{expense["amount"]:.2f}',
                expense["category"],
                expense["description"],
                expense["date"],
            ]
        )

    filename = f"expenses-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(output.getvalue(), media_type="text/csv", headers=headers)
