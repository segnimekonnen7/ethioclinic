"""
SQLAlchemy ORM models (database tables).

We use the classic SQLAlchemy style with Column() for simplicity and clarity.
The models define our data shapes and constraints — the database enforces
the constraints so bad data can't sneak past us.
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db import Base


class Role(str, enum.Enum):
    """
    Every user has exactly one role. By using a Python enum we get:
      - a short list of valid values (no typos like "admn")
      - automatic validation at the DB level (Postgres creates a real
        ENUM type so invalid values are rejected by the database)
    We inherit from `str` so JSON serialization is clean.
    """
    admin = "admin"
    receptionist = "receptionist"
    doctor = "doctor"
    patient = "patient"


class AppointmentStatus(str, enum.Enum):
    """
    Appointments move through a lifecycle. We track the state in the DB
    so we can filter by it and enforce valid transitions.
    """
    scheduled = "scheduled"
    checked_in = "checked_in"
    done = "done"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"

    # Primary key. Postgres auto-increments on insert.
    id = Column(Integer, primary_key=True)

    # `unique=True` creates a UNIQUE index so two people can't share an email.
    # The database itself enforces this — our code can't accidentally break it.
    email = Column(String, unique=True, nullable=False, index=True)

    # We store the bcrypt hash of the password, NEVER the raw password.
    # The hashing happens in the security module.
    pw_hash = Column(String, nullable=False)

    # Role defaults to 'patient' on signup. Admins promote other users.
    role = Column(Enum(Role), nullable=False, default=Role.patient)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        # Handy for debugging in the Python shell.
        return f"<User id={self.id} email={self.email} role={self.role.value}>"


class Patient(Base):
    """
    A Patient is a User who can book appointments. They may have multiple
    appointments over time. When a patient signs up, they're just a User;
    a receptionist or admin creates the Patient record later with their
    full details.
    """
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)

    # Foreign key to User. If the user is deleted, cascade the deletion
    # (though in practice we'd soft-delete).
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Real-world name, phone, date of birth for appointment context.
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    dob = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Patient id={self.id} user_id={self.user_id} name={self.full_name}>"


class Doctor(Base):
    """
    A Doctor is a User with a specialty and a physical room. When a patient
    books, they book a specific doctor at a specific time.
    """
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True)

    # Foreign key to User.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Medical specialty (e.g., "General Practice", "Cardiology").
    specialty = Column(String, nullable=False)

    # Physical location in the clinic.
    room_no = Column(String, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Doctor id={self.id} user_id={self.user_id} specialty={self.specialty}>"


class Appointment(Base):
    """
    An Appointment ties a Patient to a Doctor at a specific date/time.

    THE HEADLINE STORY:
    The __table_args__ below defines a UNIQUE constraint on (doctor_id, slot_at).
    This is the database-level defense against double-booking. When two requests
    race to insert an appointment for the same doctor at the same slot, the
    second one hits this constraint violation and the database rejects it.

    The application catches the IntegrityError and returns 409, but the database
    itself is what prevents the bad state. This is better than checking-then-inserting
    because there's always a race window between the check and the insert where
    another request could sneak in.

    See routers/appointments.py for the try/except block that catches this.
    """
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)

    # Foreign keys to Doctor and Patient.
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)

    # The date/time the appointment is scheduled for.
    slot_at = Column(DateTime, nullable=False)

    # Whether it's scheduled, checked in, done, or cancelled.
    status = Column(Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.scheduled)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # The UNIQUE constraint: a doctor can only have one appointment per time slot.
    # This is enforced by the database, not by application logic. If two requests
    # try to insert for the same (doctor_id, slot_at), the second will fail with
    # IntegrityError. We catch that and return 409.
    __table_args__ = (
        UniqueConstraint("doctor_id", "slot_at", name="uq_doctor_slot"),
    )

    def __repr__(self) -> str:
        return f"<Appointment id={self.id} doctor={self.doctor_id} patient={self.patient_id} slot={self.slot_at}>"
