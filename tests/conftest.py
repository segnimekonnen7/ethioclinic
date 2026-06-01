"""
Test configuration: fixtures for the database, Redis, and test client.

We use an in-memory SQLite database for tests (no Postgres needed) and
fakeredis for Redis. This makes tests fast and reproducible.
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
import fakeredis

# Mock the environment before importing the app
os.environ["JWT_SECRET"] = "test-secret"
os.environ["APP_ENV"] = "test"
os.environ["CORS_ORIGINS"] = "http://testserver"

from app.db import Base, get_db
from app.redis_client import get_redis
from app.main import app
from app.models import User, Role
from app.security import create_access_token


# In-memory SQLite database for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables in the test database
Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def db():
    """
    Provide a fresh database session for each test.
    Tables are created once per session (scope="function").
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def redis_client():
    """
    Provide a fakeredis client for tests.
    No network calls, fast and repeatable.
    """
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture(scope="function")
def client(db, redis_client):
    """
    Provide a TestClient with dependencies overridden to use
    the test database and fakeredis.
    """

    def override_get_db():
        yield db

    def override_get_redis():
        return redis_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_user(db):
    """
    Create a test user with the patient role.
    """
    user = User(
        email="patient@test.com",
        pw_hash="$2b$12$fake_bcrypt_hash",
        role=Role.patient,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_admin(db):
    """
    Create a test admin user.
    """
    user = User(
        email="admin@test.com",
        pw_hash="$2b$12$fake_bcrypt_hash",
        role=Role.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(auth_user):
    """
    Return auth headers for a logged-in patient.
    """
    token = create_access_token(auth_user.id, auth_user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_headers(auth_admin):
    """
    Return auth headers for a logged-in admin.
    """
    token = create_access_token(auth_admin.id, auth_admin.role.value)
    return {"Authorization": f"Bearer {token}"}
