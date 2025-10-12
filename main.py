from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dotenv import load_dotenv
import csv
from datetime import datetime
from collections import defaultdict
import matplotlib.pyplot as plt

from itsdangerous import URLSafeSerializer
import os

# Load .env file
load_dotenv()

# Get credentials from .env
USERNAME = os.getenv("APP_USERNAME")
PASSWORD = os.getenv("APP_PASSWORD")
SECRET_KEY = os.getenv("SECRET_KEY")

print("Loaded APP_USERNAME:", USERNAME)
print("Loaded APP_PASSWORD:", PASSWORD)

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
        except Exception:
            return None
    return None

def require_login(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return user

# ----------------------- CHART + EXPENSE HELPERS ------------------------

def get_monthly_totals():
    monthly_totals = defaultdict(float)
    try:
        with open(CSV_FILE, mode='r') as file:
            reader = csv.reader(file)
            for row in reader:
                amount, category, description, date_str = row
                date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                month = date_obj.strftime("%Y-%m")
                monthly_totals[month] += float(amount)
    except FileNotFoundError:
        pass
    return sorted(monthly_totals.items())

def generate_monthly_chart(monthly_totals):
    months = [month for month, _ in monthly_totals]
    totals = [total for _, total in monthly_totals]

    plt.figure(figsize=(8, 4))
    plt.bar(months, totals, color="#2e86de")
    plt.xlabel("Month")
    plt.ylabel("Total Spending (₹)")
    plt.title("Monthly Spending")
    plt.xticks(rotation=45)
    plt.tight_layout()

    chart_path = os.path.join("static", "monthly_chart.png")
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
        response.set_cookie(key="session_token", value=session_token, httponly=True)
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

    # Read expense
    expenses = []
    try:
        with open(CSV_FILE, mode='r') as file:
            reader = csv.reader(file)
            expenses = list(reader)

        #sort expenses by date (latest first) 
        expenses.sort(key=lambda x: datetime.strptime(x[3], "%Y-%m-%d %H:%M:%S"), reverse=True)            
    except Exception as e:
        print("Error reading CSV:", e)
        expenses = []

    #💰 Total Spent
    total_spent = 0.0
    try:
        with open(CSV_FILE, mode='r') as file:
            reader = csv.reader(file)
            total_spent = sum(float(row[0]) for row in reader)
    except:
        pass

    # Get monthly totals and chart
    monthly_totals = get_monthly_totals()
    chart_url = generate_monthly_chart(monthly_totals) + f"?v={datetime.now().timestamp()}"

    #
    msg = request.query_params.get("msg") 

    # Map msg to friendly text
    messages = {
    "added": "✅ Expense added successfully",
    "deleted": "🗑️ Expense deleted",
    "edited": "✏️ Expense updated"
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

    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([amount, category, description, date])

    return RedirectResponse(url="/?msg=added", status_code=302)

@app.get("/delete/{index}")
async def delete_expense(request: Request, index: int):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    try:
        # Read all expenses
        with open(CSV_FILE, mode='r') as file:
            expenses = list(csv.reader(file))

        # Sort the same way (latest first)
        sorted_expenses = sorted(
            expenses,
            key=lambda x: datetime.strptime(x[3], "%Y-%m-%d %H:%M:%S"),
            reverse=True
        )

        # Identify which entry the user wants to delete
        if 0 <= index < len(sorted_expenses):
            to_delete = sorted_expenses[index]

            # Remove the exact matching entry from the original list
            expenses.remove(to_delete)

            # Save back to CSV
            with open(CSV_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerows(expenses)

    except Exception as e:
        print("Delete error:", e)

    return RedirectResponse(url="/?msg=deleted", status_code=302)

@app.get("/edit/{index}", response_class=HTMLResponse)
async def edit_expense_form(request: Request, index: int):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    try:
        # Read all expenses
        with open(CSV_FILE, mode='r') as file:
            expenses = list(csv.reader(file))

        # Sort them same way as home page
        sorted_expenses = sorted(
            expenses,
            key=lambda x: datetime.strptime(x[3], "%Y-%m-%d %H:%M:%S"),
            reverse=True
        )

        # Pick the correct record (as per what user clicked)
        if 0 <= index < len(sorted_expenses):
            expense = sorted_expenses[index]

            # Render edit form with correct data
            return templates.TemplateResponse("edit.html", {
                "request": request,
                "index": index,
                "amount": expense[0],
                "category": expense[1],
                "description": expense[2]
            })

    except Exception as e:
        print("Error loading edit form:", e)

    return RedirectResponse(url="/", status_code=302)


@app.post("/edit/{index}")
async def save_edited_expense(
    request: Request,
    index: int,
    amount: float = Form(...),
    category: str = Form(...),
    description: str = Form("")
):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)

    try:
        # Read all expenses
        with open(CSV_FILE, mode='r') as file:
            expenses = list(csv.reader(file))

        # Sort like homepage (latest first)
        sorted_expenses = sorted(
            expenses,
            key=lambda x: datetime.strptime(x[3], "%Y-%m-%d %H:%M:%S"),
            reverse=True
        )

        # Identify entry being edited
        if 0 <= index < len(sorted_expenses):
            to_edit = sorted_expenses[index]
            old_date = to_edit[3]

            # Find the same record in original list and update
            for i, row in enumerate(expenses):
                if row == to_edit:
                    expenses[i] = [amount, category, description, old_date]
                    break

            # Save back to CSV
            with open(CSV_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerows(expenses)

    except Exception as e:
        print("Error editing expense:", e)

    return RedirectResponse(url="/?msg=edited", status_code=302)
