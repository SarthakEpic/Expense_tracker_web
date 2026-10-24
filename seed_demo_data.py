"""
Seed demo data for Expense Tracker Web.

What this does:
- Backs up existing expenses.db if it exists
- Recreates the database
- Inserts realistic demo transactions across multiple months
- Covers:
  * dashboard cards
  * income / expense mix
  * pending transactions
  * budget statuses
  * monthly / quarterly / yearly reports
  * filters by category, month, year, type, and status

Run:
    python seed_demo_data.py
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import database

DB_PATH = Path("expenses.db")
owner = None


def backup_existing_db() -> Path | None:
    if not DB_PATH.exists():
        return None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.with_name(f"expenses_backup_{stamp}.db")
    shutil.copy2(DB_PATH, backup)
    return backup


def add(days_ago: int, amount: float, category: str, description: str, ttype: str, status: str):
    created_at = (datetime.now() - timedelta(days=days_ago)).strftime(database.DATE_FORMAT)
    database.add_expense(
        owner["id"],
        amount=amount,
        category=category,
        description=description,
        transaction_type=ttype,
        status=status,
        created_at=created_at,
    )


def seed():
    # Start fresh
    if DB_PATH.exists():
        DB_PATH.unlink()
    database.init_db()

    global owner
    owner = database.get_user_by_username(os.environ.get("APP_USERNAME", "admin"))
    if owner is None:
        raise SystemExit(
            "No user found. Set APP_USERNAME (and APP_PASSWORD_HASH) or create "
            "an account first, then re-run the seeder."
        )

    rows = [
        # Current month — strong dashboard signals
        (0, 60000, "Salary", "Monthly salary", "income", "completed"),
        (1, 1250, "Food", "Cafe and groceries", "expense", "completed"),
        (2, 2400, "Bills", "Electricity bill", "expense", "completed"),
        (3, 5200, "Shopping", "Shoes and clothes", "expense", "completed"),
        (4, 4500, "Travel", "Weekend trip", "expense", "completed"),
        (5, 1800, "Food", "Lunches and snacks", "expense", "completed"),
        (6, 3100, "Bills", "Internet + mobile", "expense", "completed"),
        (7, 7500, "Shopping", "Laptop accessories", "expense", "completed"),
        (8, 4200, "Travel", "Cab rides and fuel", "expense", "completed"),
        (9, 1450, "Food", "Groceries", "expense", "completed"),
        (10, 9800, "Bills", "Rent advance", "expense", "completed"),
        (11, 2600, "Food", "Dining out", "expense", "completed"),
        (12, 2200, "Health", "Medicines and doctor", "expense", "completed"),
        (13, 1200, "Subscription", "Streaming and tools", "expense", "pending"),
        (14, 2500, "Travel", "Train ticket", "expense", "pending"),
        (15, 12000, "Freelance", "Project payment", "income", "completed"),
        (16, 3000, "Entertainment", "Movies and games", "expense", "completed"),
        (17, 1650, "Food", "Takeout", "expense", "completed"),
        (18, 4300, "Shopping", "Books and stationery", "expense", "completed"),
        (19, 5200, "Bills", "Rent remainder", "expense", "completed"),
        (20, 2100, "Food", "Weekly groceries", "expense", "completed"),
        (21, 980, "Health", "Gym and supplements", "expense", "completed"),
        (22, 700, "Misc", "Small cash expense", "expense", "pending"),
        # Previous month
        (32, 52000, "Salary", "Monthly salary", "income", "completed"),
        (33, 3200, "Food", "Groceries and eating out", "expense", "completed"),
        (35, 5100, "Bills", "Household bills", "expense", "completed"),
        (37, 8600, "Shopping", "Phone and accessories", "expense", "completed"),
        (40, 3400, "Travel", "Intercity travel", "expense", "completed"),
        (43, 2800, "Education", "Course fees", "expense", "completed"),
        (45, 8000, "Freelance", "Website work", "income", "completed"),
        (47, 1400, "Food", "Coffee and snacks", "expense", "pending"),
        # Two months ago
        (62, 50000, "Salary", "Monthly salary", "income", "completed"),
        (64, 2600, "Food", "Groceries", "expense", "completed"),
        (66, 4200, "Bills", "Internet, gas, and utilities", "expense", "completed"),
        (68, 7300, "Shopping", "Clothes", "expense", "completed"),
        (71, 2500, "Travel", "Fuel and cab", "expense", "completed"),
        (74, 1500, "Health", "Medical checkup", "expense", "completed"),
        (77, 6000, "Freelance", "Design contract", "income", "completed"),
        # Three months ago
        (92, 48000, "Salary", "Monthly salary", "income", "completed"),
        (95, 2100, "Food", "Dining and groceries", "expense", "completed"),
        (97, 3900, "Bills", "Utility payment", "expense", "completed"),
        (99, 6800, "Shopping", "Study materials", "expense", "completed"),
        (102, 2200, "Travel", "Trips", "expense", "pending"),
        (105, 5000, "Freelance", "Part-time project", "income", "completed"),
        (108, 1600, "Entertainment", "Outing", "expense", "completed"),
        # Four months ago
        (123, 47000, "Salary", "Monthly salary", "income", "completed"),
        (126, 1950, "Food", "Groceries", "expense", "completed"),
        (129, 3600, "Bills", "Electricity and internet", "expense", "completed"),
        (132, 5400, "Shopping", "Winter clothes", "expense", "completed"),
        (136, 3100, "Travel", "Bus and cab", "expense", "completed"),
        (139, 900, "Health", "Doctor visit", "expense", "completed"),
        # Five months ago
        (154, 45000, "Salary", "Monthly salary", "income", "completed"),
        (157, 2500, "Food", "Groceries", "expense", "completed"),
        (160, 2800, "Bills", "Mobile and gas", "expense", "completed"),
        (163, 6200, "Shopping", "Gadgets", "expense", "completed"),
        (166, 2900, "Travel", "Local transport", "expense", "completed"),
        (170, 7000, "Freelance", "Logo design", "income", "completed"),
    ]

    for row in rows:
        add(*row)

    # Add a few very recent entries so the dashboard feels alive "today".
    add(0, 890, "Food", "Breakfast and lunch", "expense", "completed")
    add(0, 1400, "Bills", "Pending internet payment", "expense", "pending")
    add(1, 3200, "Shopping", "Stationery and charger", "expense", "completed")


def main():
    backup = backup_existing_db()
    if backup:
        print(f"Backed up existing DB to: {backup}")

    seed()
    print("Demo data seeded successfully.")
    print("Open the app and refresh the dashboard, analytics, reports, and budgets pages.")


if __name__ == "__main__":
    main()
