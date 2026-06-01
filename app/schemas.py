"""
Pydantic request/response schemas.

These are the shapes of data sent over the wire. Pydantic validates and
serializes them, and FastAPI uses them to auto-generate OpenAPI docs.
We separate request models (from clients) and response models (to clients)
so we can exclude sensitive fields like passwords from responses.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ==== Auth ====

class SignupRequest(BaseModel):
    """Request to create a new user account."""
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    """Request to log in."""
    email: EmailStr
    password: str


class AccessTokenResponse(BaseModel):
    """Response after successful login."""
    access_token: str
    token_type: str = "bearer"


# ==== User ====

class UserResponse(BaseModel):
    """User data returned to clients. Never includes password hash."""
    id: int
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True  # Allow construction from ORM objects


class PromoteUserRequest(BaseModel):
    """Request to change a user's role."""
    role: str = Field(..., description="One of: admin, receptionist, doctor, patient")


# ==== Patient ====

class PatientCreateRequest(BaseModel):
    """Receptionist creates a patient record."""
    user_id: int
    full_name: str
    phone: Optional[str] = None
    dob: Optional[datetime] = None


class PatientResponse(BaseModel):
    """Patient data returned to clients."""
    id: int
    user_id: int
    full_name: str
    phone: Optional[str]
    dob: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ==== Doctor ====

class DoctorCreateRequest(BaseModel):
    """Admin creates a doctor record."""
    user_id: int
    specialty: str
    room_no: str


class DoctorResponse(BaseModel):
    """Doctor data returned to clients."""
    id: int
    user_id: int
    specialty: str
    room_no: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==== Appointment ====

class AppointmentCreateRequest(BaseModel):
    """Patient or receptionist books an appointment."""
    doctor_id: int
    patient_id: int
    slot_at: datetime


class AppointmentUpdateRequest(BaseModel):
    """Update appointment status or slot."""
    status: Optional[str] = None
    slot_at: Optional[datetime] = None


class AppointmentResponse(BaseModel):
    """Appointment data returned to clients."""
    id: int
    doctor_id: int
    patient_id: int
    slot_at: datetime
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==== Queue ====

class QueueCheckinRequest(BaseModel):
    """Patient checks into the queue."""
    patient_id: int


class QueueItemResponse(BaseModel):
    """One item in the queue with its position."""
    position: int
    patient_id: int
    since: datetime


class QueueResponse(BaseModel):
    """The queue for a doctor."""
    doctor_id: int
    items: list[QueueItemResponse]
    count: int
