"""
EthioClinic API — entry point.

This is the main FastAPI application that:
  1. Creates all database tables on startup
  2. Mounts authentication, user, appointment, and queue routers
  3. Provides health checks for both Postgres and Redis
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine, Base, get_db
from app.redis_client import get_redis
from app import models  # noqa: F401  (import so Base.metadata sees the tables)
from app.routers import auth, users, appointments, queue


app = FastAPI(
    title="EthioClinic API",
    description="Healthcare queue & scheduling system for Ethiopian clinics",
    version="1.0.0",
)

# CORS middleware: allow all origins for the demo. In production, you'd
# restrict this to your front-end domain only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """
    Create any tables that don't exist yet.

    This is fine for learning and early development. In a real deployment
    you use Alembic migrations instead so schema changes are versioned,
    reversible, and tracked in git.
    """
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"service": "EthioClinic API", "version": "1.0.0"}


@app.get("/health")
def health(db: Session = Depends(get_db), redis=Depends(get_redis)):
    """
    Readiness check: we're 'healthy' only if both Postgres and Redis
    respond to a ping. Kubernetes or Docker Compose can use this to
    restart unhealthy instances.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {e}")

    try:
        redis.ping()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Redis unreachable: {e}")

    return {"ok": True, "db": "up", "redis": "up"}


# Mount routers under their prefixes.
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(appointments.router)
app.include_router(queue.router)
