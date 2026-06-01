"""
EthioClinic API — entry point.

This is the main FastAPI application that:
  1. Creates all database tables on startup
  2. Mounts authentication, user, appointment, and queue routers
  3. Provides health checks for both Postgres and Redis
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.redis_client import get_redis
from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestContextMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.rate_limit import limiter
from app.routers import auth, users, appointments, queue

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production_safety()
    logger.info("EthioClinic starting", extra={"app_env": settings.app_env})
    yield
    logger.info("EthioClinic shutting down")


app = FastAPI(
    title="EthioClinic API",
    description="Healthcare queue & scheduling system for Ethiopian clinics",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware: allow all origins for the demo. In production, you'd
# restrict this to your front-end domain only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


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


@app.get("/health/live")
def liveness():
    return {"ok": True, "service": "ethioclinic-api"}


@app.get("/health/ready")
def readiness(db: Session = Depends(get_db), redis=Depends(get_redis)):
    try:
        db.execute(text("SELECT 1"))
        redis.ping()
    except Exception as exc:
        logger.exception("Readiness check failed")
        raise HTTPException(status_code=503, detail=f"Service not ready: {exc}")
    return {"ok": True}


# Mount routers under their prefixes.
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(appointments.router)
app.include_router(queue.router)
