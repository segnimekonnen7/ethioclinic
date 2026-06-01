"""
Appointment booking and management.

THE HEADLINE STORY:
This router demonstrates a database-level fix for the double-booking race condition
using a UNIQUE constraint. Two requests racing to book the same doctor at the same
time will not produce a conflict at the application level — instead, the database
itself rejects the second insert. We catch the IntegrityError and return a clean 409.

See the booking handler below for the details.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.models import User, Appointment, Doctor, Patient, AppointmentStatus
from app.schemas import AppointmentCreateRequest, AppointmentUpdateRequest, AppointmentResponse
from app.deps import get_current_user, require_role

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def book_appointment(
    req: AppointmentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Book an appointment for a patient with a doctor at a specific time.

    CRITICAL: RACE CONDITION DEFENSE

    Here's the problem we're solving: imagine two users submit appointment
    requests for the same doctor at the same time slot within milliseconds
    of each other. At the application level, both requests might:
      1. Query the database and see no conflict
      2. Both decide it's safe to proceed
      3. Both insert the same appointment

    This race condition is famously hard to catch with application logic
    (check-then-act is inherently racy). Instead, we use the database.

    The Appointment model has a UNIQUE constraint on (doctor_id, slot_at).
    The database enforces this atomically. So:
      1. Request A inserts successfully
      2. Request B tries to insert the same (doctor, time)
      3. Postgres rejects Request B's insert with an IntegrityError
      4. We catch it and return 409 Conflict

    This is the right solution because:
      - The database is the source of truth
      - There's no race window (database operations are atomic)
      - The application doesn't have to know about the constraint
      - We still return a clean HTTP error to the user

    In production, you'd also log the conflict for analytics (how often
    does this happen? is it bots?), maybe notify the patient of alternatives,
    and probably have a second-level check for overbooking (max patients
    per doctor per day).
    """

    # Verify the doctor and patient exist first.
    doctor = db.query(Doctor).filter(Doctor.id == req.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    patient = db.query(Patient).filter(Patient.id == req.patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    # Authorization: staff can book for anyone; a patient can only book for themselves.
    # We compare against patient.user_id (which links a Patient row to a User), NOT
    # patient.id (which is just the Patient table's primary key — a different entity).
    is_staff = current_user.role.value in ["admin", "receptionist"]
    is_self = patient.user_id == current_user.id
    if not is_staff and not is_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only book appointments for yourself or as staff",
        )

    # Create the appointment object.
    appointment = Appointment(
        doctor_id=req.doctor_id,
        patient_id=req.patient_id,
        slot_at=req.slot_at,
        status=AppointmentStatus.scheduled,
    )

    db.add(appointment)

    # NOW THE KEY PART: we wrap the commit in try/except to catch IntegrityError.
    #
    # If two requests race, the second one will hit the UNIQUE constraint
    # violation on (doctor_id, slot_at) and raise IntegrityError. We catch it,
    # rollback the transaction, and return 409.
    #
    # This is better than checking-then-inserting because:
    #   1. No race window between the check and the insert
    #   2. The database is the single source of truth
    #   3. We don't have to maintain a separate check in the app
    #
    # The database guarantees that only one appointment per (doctor, time) exists.
    try:
        db.commit()
        db.refresh(appointment)
        return appointment
    except IntegrityError as e:
        db.rollback()

        # Check if it's the UNIQUE constraint error we expect.
        # Postgres mentions the named constraint ("uq_doctor_slot"); SQLite
        # phrases it as "UNIQUE constraint failed: appointments.doctor_id, ...".
        # Match either so dev (SQLite) and prod (Postgres) both return a clean message.
        err = str(e).lower()
        if "uq_doctor_slot" in err or ("unique" in err and "doctor_id" in err and "slot_at" in err):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This time slot is already booked",
            )
        # Some other integrity error (shouldn't happen, but just in case).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot book appointment due to a constraint violation",
        )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get an appointment. You can view it if you're:
      - The patient
      - The doctor
      - An admin or receptionist
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Get the patient and doctor to check ownership.
    patient = db.query(Patient).filter(Patient.id == appointment.patient_id).first()
    doctor = db.query(Doctor).filter(Doctor.id == appointment.doctor_id).first()

    # Check if the current user has permission to view this appointment.
    is_patient = patient and patient.user_id == current_user.id
    is_doctor = doctor and doctor.user_id == current_user.id
    is_staff = current_user.role.value in ["admin", "receptionist"]

    if not (is_patient or is_doctor or is_staff):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    return appointment


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(
    appointment_id: int,
    req: AppointmentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update an appointment (cancel or reschedule).

    You can update if you're the patient, the doctor, or staff.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Check permissions.
    patient = db.query(Patient).filter(Patient.id == appointment.patient_id).first()
    doctor = db.query(Doctor).filter(Doctor.id == appointment.doctor_id).first()

    is_patient = patient and patient.user_id == current_user.id
    is_doctor = doctor and doctor.user_id == current_user.id
    is_staff = current_user.role.value in ["admin", "receptionist"]

    if not (is_patient or is_doctor or is_staff):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Apply updates.
    if req.status:
        appointment.status = req.status

    if req.slot_at:
        appointment.slot_at = req.slot_at

    try:
        db.commit()
        db.refresh(appointment)
        return appointment
    except IntegrityError as e:
        db.rollback()
        # Postgres mentions the named constraint ("uq_doctor_slot"); SQLite
        # phrases it as "UNIQUE constraint failed: appointments.doctor_id, ...".
        # Match either so dev (SQLite) and prod (Postgres) both return a clean message.
        err = str(e).lower()
        if "uq_doctor_slot" in err or ("unique" in err and "doctor_id" in err and "slot_at" in err):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The new time slot is already booked",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot update appointment due to a constraint violation",
        )


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    doctor_id: int = None,
    patient_id: int = None,
    status_filter: AppointmentStatus = None,
    current_user: User = Depends(require_role("admin", "receptionist")),
    db: Session = Depends(get_db),
):
    """
    List appointments (staff only). Can filter by doctor, patient, or status.
    """
    query = db.query(Appointment)

    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)

    return query.all()
