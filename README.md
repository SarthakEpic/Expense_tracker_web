# 💸 Expense Tracker Web

A lightweight personal expense tracker built with FastAPI and SQLite.  
Track daily expenses, view spending insights, generate charts, and export reports — all from a clean web interface.

---

## ✨ Features

- 🔐 Secure single-user authentication
- 💰 Add, edit, and delete expenses
- 🧠 Smart category suggestions
- 📊 Monthly, yearly, and category-based reports
- 📈 Spending charts with Matplotlib
- 📂 CSV export support
- 🛡️ CSRF protection
- 🧪 Pytest test coverage
- 🗄️ SQLite database storage

---

## 📸 Screenshots

> Add your screenshots here after uploading images.

```md
![Dashboard](screenshots/dashboard.png)
![Reports](screenshots/reports.png)
```

---

# 🛠️ Tech Stack

- FastAPI
- SQLite
- Jinja2 Templates
- Matplotlib
- Pytest
- HTML/CSS

---

# 📁 Project Structure

```text
expense-tracker-web/
│
├── main.py              # FastAPI routes and app logic
├── database.py          # SQLite setup and queries
├── create_user.py       # Generate hashed credentials
├── templates/           # Jinja2 templates
├── static/
│   └── style.css        # Styling
├── tests/               # Pytest test suite
├── requirements.txt     # Dependencies
├── .env.example         # Example environment variables
├── .gitignore
└── README.md
```

---

# 🚀 Getting Started

## 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-username/expense-tracker-web.git
cd expense-tracker-web
```

---

## 2️⃣ Create a Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / Mac

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4️⃣ Create Credentials

Run:

```bash
python create_user.py
```

This generates a local `.env` file containing:

```env
APP_USERNAME=your_username
APP_PASSWORD_HASH=your_password_hash
SECRET_KEY=your_secret_key
```

---

# ▶️ Run the Application

```bash
uvicorn main:app --reload
```

Open in browser:

```text
http://127.0.0.1:8000
```

---

# 🧪 Run Tests

```bash
python -m pytest
```

---

# 📊 Features Overview

| Feature | Description |
|---|---|
| Authentication | Secure hashed login system |
| Expense Tracking | Add, edit, delete expenses |
| Reports | Monthly & yearly summaries |
| Charts | Visual spending analytics |
| CSV Export | Export filtered data |
| SQLite Storage | Lightweight local database |

---

# 🔒 Security Notes

This project is intended for personal/local usage and learning purposes.

Do NOT commit:
- `.env`
- Database files
- Exported CSV files

The application includes:
- Password hashing
- CSRF protection
- Environment-based secrets

---

# 📦 Data Storage

- Expense data is stored in `expenses.db`
- Database files are ignored by Git
- Existing CSV data can optionally migrate into SQLite on startup

---

# 🌟 Future Improvements

- Multi-user support
- Budget tracking
- REST API endpoints
- Docker deployment
- Cloud database support
- Dark mode UI
- Advanced analytics dashboard

---

# 🤝 Contributing

Contributions, suggestions, and improvements are welcome.

Feel free to fork the repository and submit a pull request.

---

# 📄 License

This project is open-source and available under the MIT License.

---

# ⭐ Support

If you like this project, consider giving it a star on GitHub!
