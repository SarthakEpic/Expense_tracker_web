# Expense Tracker Web

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-Pytest%20Passing-brightgreen.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A self-hosted personal finance and expense tracking dashboard built with **FastAPI**, **SQLite**, and **Jinja2**. Designed for speed, data ownership, and daily usability without heavy third-party JavaScript runtimes or external database servers.

---

## Key Features

### 📒 Transaction Ledger & Cash Flow
- Record both **expenses** and **income** with custom categories, dates, merchants, and descriptions.
- Track settlement states with **completed** vs. **pending** transactions.
- Fast multi-filter queries by search keyword, category, transaction type, status, and date range (`date_from` / `date_to`).
- Multi-column sorting (newest, oldest, amount high/low, category) and paginated browsing.
- Slide-over quick action drawer for seamless transaction logging from any view.

### 🎯 Dynamic Category Budgeting
- Set and adjust custom monthly spending limits per category directly from the web interface.
- Real-time progress bars and status indicators:
  - **Safe:** Spending is below 80% of limit.
  - **Warning:** Spending is between 80% and 100%.
  - **Over Budget:** Spending exceeds monthly allocation.
- Category limits persist directly in SQLite and calculate against completed outflows for the current billing cycle.

### 📊 Analytics & Visual Trends
- **Income vs. Expense Trends:** Responsive dual-line SVG chart tracking 6-month historical trajectory.
- **Spending Pacing:** Monthly bar chart displaying actual spending alongside linear month-end projections.
- **Category Concentration:** SVG/CSS conic donut chart showing spending distribution across primary categories.
- **Net Momentum:** Sparklines calculating net savings and month-over-month percentage change.
- Zero client-side charting libraries (no Chart.js, D3, or Matplotlib dependencies) — all charts render directly via native CSS and SVG.

### 📄 Reports & CSV Exports
- Rolling summaries covering **Monthly**, **Quarterly** (last 3 months), and **Yearly** (12-month rolling) net savings.
- Filter-aware CSV export with dynamic timestamped filenames (`expenses-YYYYMMDD-HHMMSS.csv`).

### 🛡️ Security & Privacy
- **Zero Cloud Tracking:** All financial data remains in a local, single-file SQLite database on your machine.
- **PBKDF2 Password Hashing:** Credentials hashed with `hashlib.pbkdf2_hmac` (`sha256`, 120,000 iterations, random salt).
- **Cryptographically Signed Sessions:** HTTP-only cookies signed with `URLSafeTimedSerializer` and strict 7-day expiration.
- **CSRF Defense:** Double-submit cookie verification across all mutating form requests.
- **Hardened Navigation:** Open-redirect defense via server-side `Referer` host validation.

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | High-performance ASGI framework with clean dependency injection |
| **Database** | SQLite3 | Zero configuration, serverless, atomic local storage |
| **Templates** | [Jinja2](https://jinja.palletsprojects.com/) | Server-side rendered HTML with minimal client overhead |
| **Styling** | Native CSS Custom Properties | Pure CSS layout with CSS grid, flexbox, and persistent Dark/Light themes |
| **Testing** | [Pytest](https://docs.pytest.org/) + [HTTPX](https://www.python-httpx.org/) | Comprehensive integration testing for routes, auth, and calculations |

---

## Project Structure

```text
Expense_tracker_web/
├── database.py              # SQLite connection, schema initialization, and queries
├── main.py                  # FastAPI route controllers, math models, and auth
├── create_user.py           # CLI wizard to generate user credentials and .env
├── seed_demo_data.py        # Seed script with 6 months of demo financial history
├── requirements.txt         # Production and development dependencies
├── .env.example             # Template for required environment variables
├── .gitignore               # Excludes secrets, databases, and caches
├── static/
│   ├── app.js               # Theme toggle, drawer interaction, and accessibility
│   └── style.css            # Design system, charts, cards, and responsive rules
├── templates/
│   ├── base.html            # App shell with sidebar, topbar, and drawer
│   ├── dashboard.html       # KPI metrics, trend graphs, and recent activity
│   ├── transactions.html    # Full ledger with search, filtering, and pagination
│   ├── analytics.html       # Spending pacing, category stack, and cashflow bars
│   ├── budgets.html         # Budget limit controls, cards, and warning triggers
│   ├── reports.html         # Monthly/quarterly/yearly rollups and CSV export
│   ├── settings.html        # Workspace profile and preferences
│   ├── edit.html            # Transaction edit form
│   ├── login.html           # Authentication page
│   └── coming-soon.html     # Staged roadmap overview
└── tests/
    └── test_app.py          # Pytest test suite (auth, CRUD, CSRF, budgets, reports)
```

---

## Getting Started

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/SarthakEpic/Expense_tracker_web.git
cd Expense_tracker_web
```

### 2. Create and Activate a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment & Admin User
Run the setup utility to generate your application secrets and password hash:

```bash
python create_user.py
```

Follow the prompts to specify your username and password. This will generate a local `.env` file:
```env
APP_USERNAME=your_username
APP_PASSWORD_HASH=pbkdf2_sha256$120000$salt$hash
SECRET_KEY=generated_random_secret_token
```

> **Note:** Never commit `.env` or `expenses.db` to source control.

### 5. (Optional) Seed Demo Data
To explore the dashboard with realistic multi-month spending, category breakdowns, and pending items:
```bash
python seed_demo_data.py
```
*(This automatically backs up any existing `expenses.db` before seeding.)*

### 6. Start the Server
```bash
uvicorn main:app --reload
```

Open your browser and navigate to:
```text
http://127.0.0.1:8000
```
Log in using the credentials you defined in Step 4.

---

## Environment Configuration

| Variable | Required | Description |
|---|---|---|
| `APP_USERNAME` | **Yes** | The username required to log in |
| `APP_PASSWORD_HASH` | **Yes** | Salted PBKDF2 hash generated by `create_user.py` |
| `SECRET_KEY` | **Yes** | 32+ character random secret used for session signing |

---

## Database Architecture & Migration

The application uses local SQLite storage (`expenses.db`). When the app boots, `init_db()` in `database.py` runs automatically and applies performance indexes:

- `idx_expenses_created_at`: Speeds up date-range filtering and sorting.
- `idx_expenses_category`: Accelerates category aggregation queries.
- `idx_expenses_type_status`: Optimizes completed vs. pending cashflow rollups.

### Automatic CSV Migration
If a legacy `expenses.csv` file exists in the root folder and the database is empty, the application automatically imports all valid records into SQLite upon initial launch.

---

## Running Automated Tests

The test suite runs on `pytest` and uses an isolated temporary SQLite database for every test:

```bash
python -m pytest -v
```

Tests cover:
- Authentication & invalid credential rejection
- Session expiration and 401 redirect enforcement
- CSRF token validation and rejection of unauthenticated mutating requests
- Add, Edit, and Delete transaction lifecycle
- Open-redirect protection on navigation referrers
- Financial math calculations (percentage growth with negative baselines)
- 12-month rolling calculation correctness
- Interactive budget creation and deletion endpoints

---

## Roadmap

- [x] Single-user authentication & session timeout
- [x] Multi-criteria filtering, sorting, and pagination
- [x] Native SVG & CSS responsive charts
- [x] Persistent category budgeting & status tracking
- [ ] Multi-tenant user registration and workspace isolation
- [ ] Recurring subscription auto-logging
- [ ] REST API endpoints with bearer token auth
- [ ] Docker container and Docker Compose configuration

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
