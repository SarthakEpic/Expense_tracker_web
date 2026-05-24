from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dotenv import load_dotenv
import csv
from datetime import datetime
from collections import defaultdict
import uuid
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from itsdangerous import BadSignature, URLSafeSerializer
import os

# Load .env file
load_dotenv()

# Get credentials from .env
USERNAME = os.getenv("APP_USERNAME")
PASSWORD = os.getenv("APP_PASSWORD")
SECRET_KEY = os.getenv("SECRET_KEY")

if not USERNAME or not PASSWORD or not SECRET_KEY:
    raise RuntimeError("APP_USERNAME, APP_PASSWORD, and SECRET_KEY must be set in .env")

# Session token signer
serializer = URLSafeSerializer(SECRET_KEY)

app = FastAPI()

# Static and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CSV_FILE = "expenses.csv"

# ----------------------- SESSION HELPERS ------------------------

def get_session_user(request: Request):
    session_cookie = request.cookies.get("session_token")
    if session_cookie:
        try:
            user = serializer.loads(session_cookie)
            if user == USERNAME:
                return user
        except BadSignature:
            return None
    return None

def require_login(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return user

# ----------------------- CHART + EXPENSE HELPERS ------------------------

def parse_expense_row(row):
    if len(row) == 5:
        expense_id, amount, category, description, date_str = row
    elif len(row) == 4:
        amount, category, description, date_str = row
        expense_id = str(uuid.uuid4())
    else:
        return None

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return {
            "id": expense_id,
            "amount": float(amount),
            "category": category,
            "description": description,
            "date": date_str,
            "date_obj": date_obj
        }
    except (TypeError, ValueError):
        return None

def read_expenses():
    expenses = []
    needs_rewrite = False
    try:
        with open(CSV_FILE, mode="r", newline="") as file:
            reader = csv.reader(file)
            for row in reader:
                expense = parse_expense_row(row)
                if expense:
                    expenses.append(expense)
                    if len(row) == 4:
                        needs_rewrite = True
    except FileNotFoundError:
        return []

    if needs_rewrite:
        write_expenses(expenses)

    return expenses

def write_expenses(expenses):
    with open(CSV_FILE, mode="w", newline="") as file:
        writer = csv.writer(file)
        for expense in expenses:
            writer.writerow([
                expense["id"],
                f'{expense["amount"]:.2f}',
                expense["category"],
                expense["description"],
                expense["date"]
            ])

def find_expense(expenses, expense_id):
    return next((expense for expense in expenses if expense["id"] == expense_id), None)

def get_monthly_totals():
    monthly_totals = defaultdict(float)
    for expense in read_expenses():
        month = expense["date_obj"].strftime("%Y-%m")
        monthly_totals[month] += expense["amount"]
    return sorted(monthly_totals.items())

def generate_monthly_chart(monthly_totals):
    chart_path = os.path.join("static", "monthly_chart.png")

    if not monthly_totals:
        plt.figure(figsize=(8, 4))
        plt.text(0.5, 0.5, "No expenses yet", ha="center", va="center", fontsize=14)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        return "/static/monthly_chart.png"

    months = [month for month, _ in monthly_totals]
    totals = [total for _, total in monthly_totals]

    plt.figure(figsize=(8, 4))
    plt.bar(months, totals, color="#2e86de")
    plt.xlabel("Month")
    plt.ylabel("Total Spending (₹)")
    plt.title("Monthly Spending")
    plt.xticks(rotation=45)
    plt.tight_layout()

    plt.savefig(chart_path)
    plt.close()
    return "/static/monthly_chart.png"

# ----------------------- ROUTES ------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == USERNAME and password == PASSWORD:
        response = RedirectResponse(url="/", status_code=302)
        session_token = serializer.dumps(username)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            samesite="lax"
        )
        return response
    else:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "❌ Invalid username or password"
        })

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    expenses = sorted(read_expenses(), key=lambda x: x["date_obj"], reverse=True)
    total_spent = sum(expense["amount"] for expense in expenses)

    # Get monthly totals and chart
    monthly_totals = get_monthly_totals()
    chart_url = generate_monthly_chart(monthly_totals) + f"?v={datetime.now().timestamp()}"

    #
    msg = request.query_params.get("msg") 

    # Map msg to friendly text
    messages = {
    "added": "Expense added successfully",
    "deleted": "Expense deleted",
    "edited": "Expense updated",
    "invalid_amount": "Amount must be greater than zero"
    }
    message_text = messages.get(msg, "")

    # Render template with message
    return templates.TemplateResponse("index.html", {
        "request": request,
        "message": message_text,
        "expenses": expenses,
        "monthly_totals": monthly_totals,
        "chart_url": chart_url,
        "total_spent": total_spent
    })

@app.post("/add")
async def add_expense(
    request: Request,
    amount: float = Form(...),
    category: str = Form(...),
    description: str = Form("")
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    if amount <= 0:
        return RedirectResponse(url="/?msg=invalid_amount", status_code=302)

    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([str(uuid.uuid4()), f"{amount:.2f}", category.strip(), description.strip(), date])

    return RedirectResponse(url="/?msg=added", status_code=302)

@app.post("/delete/{expense_id}")
async def delete_expense(request: Request, expense_id: str):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    expenses = read_expenses()
    updated_expenses = [expense for expense in expenses if expense["id"] != expense_id]
    if len(updated_expenses) != len(expenses):
        write_expenses(updated_expenses)

    return RedirectResponse(url="/?msg=deleted", status_code=302)

@app.get("/edit/{expense_id}", response_class=HTMLResponse)
async def edit_expense_form(request: Request, expense_id: str):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    expense = find_expense(read_expenses(), expense_id)
    if expense:
        return templates.TemplateResponse("edit.html", {
            "request": request,
            "expense_id": expense_id,
            "amount": f'{expense["amount"]:.2f}',
            "category": expense["category"],
            "description": expense["description"]
        })

    return RedirectResponse(url="/", status_code=302)


@app.post("/edit/{expense_id}")
async def save_edited_expense(
    request: Request,
    expense_id: str,
    amount: float = Form(...),
    category: str = Form(...),
    description: str = Form("")
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    if amount <= 0:
        return RedirectResponse(url=f"/edit/{expense_id}", status_code=302)

    expenses = read_expenses()
    for expense in expenses:
        if expense["id"] == expense_id:
            expense["amount"] = amount
            expense["category"] = category.strip()
            expense["description"] = description.strip()
            write_expenses(expenses)
            break

    return RedirectResponse(url="/?msg=edited", status_code=302)
