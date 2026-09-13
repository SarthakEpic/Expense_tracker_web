# Expense Tracker Web

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-Pytest%20Passing-brightgreen.svg)](tests/)

A self-hosted personal finance and expense tracking dashboard built with **FastAPI**, **SQLite**, and **Jinja2**. Designed for speed, data ownership, and daily usability without heavy third-party JavaScript runtimes or external database servers. Runs locally on SQLite and deploys free to the cloud on Postgres — see [DEPLOY.md](DEPLOY.md).

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/SarthakEpic/Expense_tracker_web)

---

## Key Features

### 👥 Multi-User Accounts
- **Private ledgers per person:** every expense, income entry, and budget belongs to its owner — users never see each other's data.
- **Invite-only workspace:** the first account is created via `/register` (or seeded from env credentials); after that, only the admin can add users — no public sign-up on a money app.
- **Admin controls in Settings:** add users, reset a forgotten password for any member (that's the built-in "forgot password" flow), and delete accounts along with their data.
- **Per-user defaults:** each new account starts with its own budget limits, fully editable.

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
- **Zero Cloud Tracking:** All financial data remains in your own database (local SQLite file, or your own Neon Postgres in the cloud).
- **PBKDF2 Password Hashing:** Credentials hashed with `hashlib.pbkdf2_hmac` (`sha256`, 120,000 iterations, random salt).
- **In-App Credential Management:** Change username and password from **Settings → Login credentials** — stored in the database, effective immediately, no redeploy.
- **Invite-Only Access:** No open registration; the admin manages who gets an account, with brute-force lockout on repeated failed logins.
- **Brute-Force Lockout:** Repeated failed logins trigger an escalating time lockout per IP + username.
- **Cryptographically Signed Sessions:** HTTP-only cookies signed with `URLSafeTimedSerializer` and strict 7-day expiration.
- **CSRF Defense:** Double-submit cookie verification across all mutating form requests.
- **Hardened Navigation:** Open-redirect defense via server-side `Referer` host validation.
- **Security Headers:** `nosniff`, clickjacking protection, referrer policy, and `noindex` on every response.

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | High-performance ASGI framework with clean dependency injection |
| **Database** | SQLite3 (local) · [PostgreSQL](https://www.postgresql.org/) via [Neon](https://neon.com) (cloud) | Zero configuration locally; durable free-tier storage in the cloud |
| **Templates** | [Jinja2](https://jinja.palletsprojects.com/) | Server-side rendered HTML with minimal client overhead |
| **Styling** | Native CSS Custom Properties | Pure CSS layout with CSS grid, flexbox, and persistent Dark/Light themes |
| **Testing** | [Pytest](https://docs.pytest.org/) + [HTTPX](https://www.python-httpx.org/) | Comprehensive integration testing for routes, auth, and calculations |
| **Hosting** | [Render](https://render.com/docs/free) | Free web service with GitHub auto-deploy (see [DEPLOY.md](DEPLOY.md)) |

---

## Project Structure

```text
Expense_tracker_web/
├── database.py              # SQLite/Postgres connection, schema init, and queries
├── main.py                  # FastAPI route controllers, math models, and auth
├── create_user.py           # CLI wizard to generate user credentials and .env
├── seed_demo_data.py        # Seed script with 6 months of demo financial history
├── requirements.txt         # Production and development dependencies
├── render.yaml              # Render Blueprint for one-click free deployment
├── DEPLOY.md                # Step-by-step free deployment guide (Render + Neon)
├── .env.example             # Template for required environment variables
├── .gitignore               # Excludes secrets, databases, and caches
├── .github/
│   └── workflows/ci.yml     # CI: pytest on both SQLite and Postgres
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
    ├── test_app.py          # Pytest test suite (auth, CRUD, CSRF, budgets, reports)
    └── conftest.py          # Test isolation for SQLite and Postgres runs
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
| `DATABASE_URL` | No | Postgres connection string. Unset = local SQLite; set = cloud Postgres (used in deployment) |
| `TZ` | No | Timezone for transaction timestamps (e.g. `Asia/Kolkata`; set automatically by the Render blueprint) |

---

## Deployment

The app deploys free to **Render** (app) + **Neon** (Postgres) — no credit card, data persists, and every push to `main` auto-deploys. The full walkthrough is in [DEPLOY.md](DEPLOY.md):

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/SarthakEpic/Expense_tracker_web)

Local development is unaffected: without `DATABASE_URL` the app keeps using the local SQLite file.

---

## Database Architecture & Migration

Locally the application uses SQLite storage (`expenses.db`); cloud deployments use the same schema on Postgres. When the app boots, `init_db()` in `database.py` runs automatically, creates tables/indexes idempotently on either engine, and applies performance indexes:

- `idx_expenses_created_at`: Speeds up date-range filtering and sorting.
- `idx_expenses_category`: Accelerates category aggregation queries.
- `idx_expenses_type_status`: Optimizes completed vs. pending cashflow rollups.

### Automatic CSV Migration
If a legacy `expenses.csv` file exists in the root folder and the database is empty, the application automatically imports all valid records into SQLite upon initial launch.

---

## Running Automated Tests

The test suite runs on `pytest` and uses an isolated temporary SQLite database for every test. The same suite can validate the Postgres engine by setting `DATABASE_URL` (see [DEPLOY.md](DEPLOY.md)):

```bash
python -m pytest -v

# Optional: run the suite against Postgres
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/expense_test python -m pytest -v
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

## License & Rights

Copyright &copy; 2026. All rights reserved.

This project is currently private and reserved for personal and evaluation use. Commercial distribution, public redistribution, or unauthorized mirroring without explicit prior permission is strictly prohibited. Formal open-source licensing will be determined and published in a future release.
