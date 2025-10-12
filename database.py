from sqlmodel import SQLModel, create_engine, Session

# SQLite database file
DATABASE_URL = "sqlite:///expenses.db"
engine = create_engine(DATABASE_URL, echo=False)

# Call this once when app starts
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Reusable DB session
def get_session():
    return Session(engine)

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Expense(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    amount: float
    category: str
    description: Optional[str] = ""
    timestamp: datetime = Field(default_factory=datetime.now)