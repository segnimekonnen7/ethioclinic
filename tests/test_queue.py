"""
Tests for the Redis queue system.
"""

import pytest
from app.models import User, Role, Patient, Doctor


@pytest.fixture
def setup_queue_data(db, auth_user, auth_admin):
    """
    Helper to set up a doctor and a patient for queue tests.
    """
    # Create a doctor
    doctor_user = User(
        email="doctor@test.com",
        pw_hash="$2b$12$fake",
        role=Role.doctor,
    )
    db.add(doctor_user)
    db.commit()
    db.refresh(doctor_user)

    doctor = Doctor(
        user_id=doctor_user.id,
        specialty="General Practice",
        room_no="101",
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)

    # Create a patient
    patient = Patient(
        user_id=auth_user.id,
        full_name="Test Patient",
        phone="555-0001",
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    return {"doctor": doctor, "patient": patient}


def test_checkin_success(client, auth_headers, setup_queue_data):
    """Test a patient checking into the queue."""
    doctor = setup_queue_data["doctor"]
    patient = setup_queue_data["patient"]

    response = client.post(
        f"/queue/{doctor.id}/checkin",
        headers=auth_headers,
        json={"patient_id": patient.id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["patient_id"] == patient.id
    assert data["newly_added"] is True


def test_checkin_idempotent(client, auth_headers, setup_queue_data):
    """Test that checking in twice is idempotent."""
    doctor = setup_queue_data["doctor"]
    patient = setup_queue_data["patient"]

    # First checkin
    response1 = client.post(
        f"/queue/{doctor.id}/checkin",
        headers=auth_headers,
        json={"patient_id": patient.id},
    )
    assert response1.status_code == 200
    assert response1.json()["newly_added"] is True

    # Second checkin (should not add again)
    response2 = client.post(
        f"/queue/{doctor.id}/checkin",
        headers=auth_headers,
        json={"patient_id": patient.id},
    )
    assert response2.status_code == 200
    assert response2.json()["newly_added"] is False


def test_get_queue(client, db, auth_user, admin_headers, setup_queue_data):
    """Test viewing the queue for a doctor."""
    doctor = setup_queue_data["doctor"]
    patient = setup_queue_data["patient"]

    # Check in the patient
    client.post(
        f"/queue/{doctor.id}/checkin",
        headers=admin_headers,
        json={"patient_id": patient.id},
    )

    # Get the queue
    response = client.get(
        f"/queue/{doctor.id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["doctor_id"] == doctor.id
    assert data["count"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["patient_id"] == patient.id
    assert data["items"][0]["position"] == 1


def test_next_patient(client, db, auth_user, admin_headers, setup_queue_data):
    """Test calling the next patient from the queue."""
    doctor = setup_queue_data["doctor"]
    patient = setup_queue_data["patient"]

    # Check in the patient
    client.post(
        f"/queue/{doctor.id}/checkin",
        headers=admin_headers,
        json={"patient_id": patient.id},
    )

    # Verify the patient is in the queue
    queue_response = client.get(
        f"/queue/{doctor.id}",
        headers=admin_headers,
    )
    assert queue_response.json()["count"] == 1

    # Call next
    next_response = client.post(
        f"/queue/{doctor.id}/next",
        headers=admin_headers,
    )
    assert next_response.status_code == 200
    data = next_response.json()
    assert data["ok"] is True
    assert data["patient_id"] == patient.id

    # Verify the queue is now empty
    queue_response = client.get(
        f"/queue/{doctor.id}",
        headers=admin_headers,
    )
    assert queue_response.json()["count"] == 0


def test_next_patient_empty_queue(client, admin_headers, setup_queue_data):
    """Test calling next on an empty queue."""
    doctor = setup_queue_data["doctor"]

    response = client.post(
        f"/queue/{doctor.id}/next",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["patient_id"] is None
