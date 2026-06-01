"""
Database plumbing: engine, session factory, and a FastAPI dependency
that hands out a fresh Session per request and cleans it up afterwards.

We use SQLAlchemy 2.x as the ORM. The 'engine' is a connection pool to
Postgres; the 'Session' is one unit of work (one DB conversation) — we
create one per request so transactions are cleanly scoped.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# DATABASE_URL is read from the environment so we can point at a real
# Postgres in Docker and at a throwaway SQLite in tests. 'postgresql+psycopg://'
# tells SQLAlchemy to use the psycopg (v3) driver.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/ethioclinic",
)

# pool_pre_ping=True means SQLAlchemy sends a quick "are you still there?"
# ping before handing out a pooled connection. Prevents 'server closed
# connection unexpectedly' errors when Postgres restarts.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

# sessionmaker() is a factory. Calling SessionLocal() returns a new Session.
# autoflush=False stops SQLAlchemy from flushing writes on every query —
# it gives us more control and makes transactional behavior predictable.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Every model we create inherits from Base. SQLAlchemy collects them on
# Base.metadata so we can later ask it to 'create every table'.
Base = declarative_base()


def get_db():
    """
    FastAPI dependency. Any route that adds `db: Session = Depends(get_db)`
    gets a fresh session, and we guarantee it's closed even if the route
    raises an exception. This is the standard FastAPI + SQLAlchemy pattern.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
