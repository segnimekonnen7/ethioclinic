from datetime import datetime, timedelta

from jose import jwt

from app.models import User, Role, Doctor, Patient


def test_promote_user_invalid_role_returns_422(client, db, admin_headers):
    user = User(email="target@test.com", pw_hash="$2b$12$fake", role=Role.patient)
    db.add(user)
    db.commit()
    db.refresh(user)

    response = client.patch(
        f"/users/{user.id}/role",
        headers=admin_headers,
        json={"role": "superadmin"},
    )
    assert response.status_code == 422


def test_update_appointment_requires_fields(client, db, auth_headers, auth_user):
    doctor_user = User(email="docx@test.com", pw_hash="$2b$12$fake", role=Role.doctor)
    db.add(doctor_user)
    db.commit()
    db.refresh(doctor_user)

    doctor = Doctor(user_id=doctor_user.id, specialty="General", room_no="102")
    db.add(doctor)
    db.commit()
    db.refresh(doctor)

    patient = Patient(user_id=auth_user.id, full_name="Patient", phone="555-1212")
    db.add(patient)
    db.commit()
    db.refresh(patient)

    create_resp = client.post(
        "/appointments",
        headers=auth_headers,
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "slot_at": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        },
    )
    assert create_resp.status_code == 201
    appointment_id = create_resp.json()["id"]

    update_resp = client.patch(
        f"/appointments/{appointment_id}",
        headers=auth_headers,
        json={},
    )
    assert update_resp.status_code == 422


def test_invalid_token_subject_returns_401(client):
    bad_token = jwt.encode({"sub": "abc", "role": "patient"}, "test-secret", algorithm="HS256")
    response = client.get("/users/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert response.status_code == 401


def test_doctor_cannot_view_other_doctor_queue(client, db):
    doctor1_user = User(email="doc1@test.com", pw_hash="$2b$12$fake", role=Role.doctor)
    doctor2_user = User(email="doc2@test.com", pw_hash="$2b$12$fake", role=Role.doctor)
    db.add(doctor1_user)
    db.add(doctor2_user)
    db.commit()
    db.refresh(doctor1_user)
    db.refresh(doctor2_user)

    doctor1 = Doctor(user_id=doctor1_user.id, specialty="General", room_no="201")
    doctor2 = Doctor(user_id=doctor2_user.id, specialty="General", room_no="202")
    db.add(doctor1)
    db.add(doctor2)
    db.commit()
    db.refresh(doctor1)
    db.refresh(doctor2)

    token = jwt.encode({"sub": str(doctor1_user.id), "role": "doctor"}, "test-secret", algorithm="HS256")
    response = client.get(f"/queue/{doctor2.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
