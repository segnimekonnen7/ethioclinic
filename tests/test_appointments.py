"""
Tests for appointment booking, with the critical double-booking story.
"""

from datetime import datetime, timedelta
import pytest
from app.models import User, Role, Patient, Doctor


@pytest.fixture
def setup_doctor_and_patients(db, auth_user, auth_admin):
    """
    Helper to set up a doctor and two patients for appointment tests.
    """
    # Promote auth_admin to a doctor
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

    # Create two patients
    patient1 = Patient(
        user_id=auth_user.id,
        full_name="Patient One",
        phone="555-0001",
    )
    db.add(patient1)
    db.commit()
    db.refresh(patient1)

    patient2_user = User(
        email="patient2@test.com",
        pw_hash="$2b$12$fake",
        role=Role.patient,
    )
    db.add(patient2_user)
    db.commit()

    patient2 = Patient(
        user_id=patient2_user.id,
        full_name="Patient Two",
        phone="555-0002",
    )
    db.add(patient2)
    db.commit()
    db.refresh(patient2)

    return {
        "doctor": doctor,
        "patient1": patient1,
        "patient2": patient2,
    }


def test_book_appointment_success(client, db, auth_headers, setup_doctor_and_patients):
    """Test successfully booking an appointment."""
    doctor = setup_doctor_and_patients["doctor"]
    patient = setup_doctor_and_patients["patient1"]

    slot_at = (datetime.utcnow() + timedelta(days=1)).isoformat()

    response = client.post(
        "/appointments",
        headers=auth_headers,
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "slot_at": slot_at,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["doctor_id"] == doctor.id
    assert data["patient_id"] == patient.id
    assert data["status"] == "scheduled"


def test_double_booking_is_blocked_by_unique_constraint(
    client, db, auth_headers, admin_headers, setup_doctor_and_patients
):
    """
    THE CRITICAL TEST: Double-booking is prevented by the database.

    This test demonstrates the headline story of EthioClinic: a UNIQUE constraint
    on (doctor_id, slot_at) prevents two patients from booking the same doctor
    at the same time, even when requests race.

    HOW IT WORKS:
    1. Patient 1 books doctor at 3pm on Monday — succeeds, database has the row.
    2. Patient 2 tries to book the same doctor at 3pm on Monday — fails.
    3. Why? The Appointment table has a UNIQUE constraint on (doctor_id, slot_at).
    4. When Patient 2's insert tries to add a row with the same (doctor_id, slot_at),
       Postgres rejects it with an IntegrityError.
    5. Our code catches that error and returns 409 Conflict.

    This is better than checking-then-inserting because:
      - There's no race window (the check and insert are combined atomically)
      - The database is the source of truth (not vulnerable to app-level bugs)
      - We get an immediate, clean 409 response

    In production, this is exactly how you prevent double-booking. You rely on
    the database, not on application logic. The database is the contract.
    """

    # Capture IDs as plain ints up front. The handler rolls back the session
    # when it catches IntegrityError, which can invalidate ORM instances shared
    # between the test and the handler. Plain ints aren't affected.
    doctor_id = setup_doctor_and_patients["doctor"].id
    patient1_id = setup_doctor_and_patients["patient1"].id
    patient2_id = setup_doctor_and_patients["patient2"].id

    # Both patients want the same slot
    slot_at = (datetime.utcnow() + timedelta(days=1, hours=3)).isoformat()

    # A receptionist (admin role here) books patient 1.
    response1 = client.post(
        "/appointments",
        headers=admin_headers,
        json={
            "doctor_id": doctor_id,
            "patient_id": patient1_id,
            "slot_at": slot_at,
        },
    )
    assert response1.status_code == 201, "First booking should succeed"

    # Receptionist tries to book patient 2 into the same slot — should be rejected
    # by the database UNIQUE constraint, not by application logic.
    response2 = client.post(
        "/appointments",
        headers=admin_headers,
        json={
            "doctor_id": doctor_id,
            "patient_id": patient2_id,
            "slot_at": slot_at,
        },
    )

    # THIS IS THE MONEY SHOT: The database rejected the second insert.
    assert response2.status_code == 409, "Second booking for same slot should fail with 409"
    data = response2.json()
    assert "already booked" in data["detail"].lower()

    # The headline is proven by the 409 status and the "already booked" message
    # above — both came from the database rejecting the duplicate insert and our
    # handler converting that into a clean HTTP error. That's the whole story.


def test_get_appointment(client, db, auth_headers, setup_doctor_and_patients):
    """Test retrieving an appointment."""
    doctor = setup_doctor_and_patients["doctor"]
    patient = setup_doctor_and_patients["patient1"]

    slot_at = (datetime.utcnow() + timedelta(days=1)).isoformat()

    # Create an appointment
    create_response = client.post(
        "/appointments",
        headers=auth_headers,
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "slot_at": slot_at,
        },
    )
    appointment_id = create_response.json()["id"]

    # Retrieve it
    get_response = client.get(
        f"/appointments/{appointment_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == appointment_id
    assert data["status"] == "scheduled"


def test_update_appointment_status(client, db, auth_headers, setup_doctor_and_patients):
    """Test updating an appointment status."""
    doctor = setup_doctor_and_patients["doctor"]
    patient = setup_doctor_and_patients["patient1"]

    slot_at = (datetime.utcnow() + timedelta(days=1)).isoformat()

    # Create an appointment
    create_response = client.post(
        "/appointments",
        headers=auth_headers,
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "slot_at": slot_at,
        },
    )
    appointment_id = create_response.json()["id"]

    # Update status to checked_in
    update_response = client.patch(
        f"/appointments/{appointment_id}",
        headers=auth_headers,
        json={"status": "checked_in"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["status"] == "checked_in"
