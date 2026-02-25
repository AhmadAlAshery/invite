from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.declarative import declarative_base
from pathlib import Path

# Ensure db directory exists
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "sqlite.db"
Base = declarative_base()

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session - used in FastAPI dependencies"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
