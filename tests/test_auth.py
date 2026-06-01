"""
Tests for authentication routes.
"""


def test_signup(client):
    """Test creating a new user account."""
    response = client.post(
        "/auth/signup",
        json={"email": "newuser@test.com", "password": "securepassword123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@test.com"
    assert data["role"] == "patient"
    assert "pw_hash" not in data  # Password never sent back


def test_signup_duplicate_email(client):
    """Test that duplicate emails are rejected."""
    client.post(
        "/auth/signup",
        json={"email": "test@test.com", "password": "password123"},
    )
    # Try to sign up with the same email again
    response = client.post(
        "/auth/signup",
        json={"email": "test@test.com", "password": "different123"},
    )
    assert response.status_code == 409


def test_login(client):
    """Test logging in with correct credentials."""
    # First, sign up
    client.post(
        "/auth/signup",
        json={"email": "user@test.com", "password": "password123"},
    )
    # Then, log in
    response = client.post(
        "/auth/login",
        json={"email": "user@test.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    """Test that wrong passwords are rejected."""
    client.post(
        "/auth/signup",
        json={"email": "user@test.com", "password": "password123"},
    )
    response = client.post(
        "/auth/login",
        json={"email": "user@test.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    """Test that nonexistent users return 401."""
    response = client.post(
        "/auth/login",
        json={"email": "doesntexist@test.com", "password": "password123"},
    )
    assert response.status_code == 401
