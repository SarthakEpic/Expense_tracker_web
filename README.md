# Expense Tracker Web

A small FastAPI web app for tracking personal expenses. It supports login, SQLite-backed expense storage, category suggestions, filters, reports, charts, and CSV export.

## Features

- Single-user login with hashed password support
- SQLite database storage
- Add, edit, and delete expenses
- Category suggestions based on previous entries
- Filter expenses by category, month, and year
- Monthly, yearly, and category totals
- Monthly spending chart generated with Matplotlib
- CSV export for the currently filtered view
- CSRF protection on form submissions
- Pytest coverage for the main user flows

## Project Structure

```text
.
├── main.py              # FastAPI routes, auth, CSRF, reports, export
├── database.py          # SQLite setup and expense queries
├── create_user.py       # Helper to create hashed .env credentials
├── templates/           # Jinja pages
├── static/style.css     # App styling
├── tests/               # Pytest tests
├── requirement.txt      # Python dependencies
└── .env.example         # Example environment config
```

## Setup

Create and activate a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirement.txt
```

Create your local credentials:

```bash
python create_user.py
```

This writes a local `.env` file with `APP_USERNAME`, `APP_PASSWORD_HASH`, and `SECRET_KEY`.

## Run

```bash
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Test

```bash
python -m pytest
```

## Data Notes

The app stores live data in `expenses.db`, which is intentionally ignored by Git. If an old `expenses.csv` file exists, the app can migrate it into SQLite on startup when the database is empty.

## Security Notes

Do not commit `.env`, database files, or exported CSV files. The app is designed for a local/small personal tracker, not as a production multi-user finance system.
