"""
User management routes.

Authenticated users can see their own profile. Admins can promote users
to other roles and create Patient or Doctor records.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, Patient, Doctor
from app.schemas import UserResponse, PromoteUserRequest, PatientCreateRequest, PatientResponse, DoctorCreateRequest, DoctorResponse
from app.deps import get_current_user, require_role

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Get the current logged-in user's profile.
    """
    return current_user


@router.patch("/{user_id}/role", response_model=UserResponse)
def promote_user(
    user_id: int,
    req: PromoteUserRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Admin-only: change a user's role.

    This is how we promote patients to doctors, or give admin privileges.
    In a real system, you'd audit these changes (who changed it, when, why).
    """

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Convert the string role to the enum.
    try:
        from app.models import Role
        user.role = Role(req.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {req.role}",
        )

    db.commit()
    db.refresh(user)
    return user


@router.post("/patients", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    req: PatientCreateRequest,
    current_user: User = Depends(require_role("admin", "receptionist")),
    db: Session = Depends(get_db),
):
    """
    Admin or receptionist: create a Patient record for a User.

    A Patient ties a User to clinical details like name, phone, and DOB.
    A User can exist without a Patient record (e.g., a doctor), but a
    Patient must have a corresponding User.
    """

    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check if a Patient record already exists for this user.
    existing = db.query(Patient).filter(Patient.user_id == req.user_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient record already exists for this user",
        )

    patient = Patient(
        user_id=req.user_id,
        full_name=req.full_name,
        phone=req.phone,
        dob=req.dob,
    )

    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.post("/doctors", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED)
def create_doctor(
    req: DoctorCreateRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Admin-only: create a Doctor record for a User.

    A Doctor is a User with a specialty and a room number. Patients book
    appointments with specific doctors.
    """

    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check if a Doctor record already exists for this user.
    existing = db.query(Doctor).filter(Doctor.user_id == req.user_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor record already exists for this user",
        )

    doctor = Doctor(
        user_id=req.user_id,
        specialty=req.specialty,
        room_no=req.room_no,
    )

    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor
