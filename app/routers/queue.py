"""
Queue management using Redis.

Patients check in to a queue when they arrive. The queue is a Redis sorted
set (a priority queue) where the score is the enqueue timestamp. This lets
us answer "am I next?" (ZRANK) and "who's next?" (ZPOPMIN) efficiently
without DB round-trips.

Queue key: queue:doctor:{doctor_id}
Events channel: queue:doctor:{doctor_id}:events
"""

import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, Doctor, Patient
from app.schemas import QueueCheckinRequest, QueueResponse, QueueItemResponse
from app.deps import get_current_user, require_role
from app.redis_client import get_redis

router = APIRouter(prefix="/queue", tags=["queue"])


def get_queue_key(doctor_id: int) -> str:
    """Helper to construct the Redis key for a doctor's queue."""
    return f"queue:doctor:{doctor_id}"


def get_events_channel(doctor_id: int) -> str:
    """Helper to construct the Redis pub/sub channel for queue events."""
    return f"queue:doctor:{doctor_id}:events"


@router.post("/{doctor_id}/checkin")
def checkin(
    doctor_id: int,
    req: QueueCheckinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Check in to the queue. The patient is added to a sorted set with the
    current timestamp as the score (position in queue).

    The endpoint is idempotent: if the patient is already in the queue,
    adding them again does nothing (Redis ZADD NX).
    """

    # Verify the doctor exists.
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    # Verify the patient exists and belongs to the current user (or user is staff).
    patient = db.query(Patient).filter(Patient.id == req.patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    if patient.user_id != current_user.id and current_user.role.value not in ["admin", "receptionist"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only check in yourself",
        )

    # Add to the queue with the current timestamp as the score.
    queue_key = get_queue_key(doctor_id)
    score = time.time()

    # NX means "only add if not already present" (idempotent).
    added = redis.zadd(queue_key, {str(req.patient_id): score}, nx=True)

    # Publish a "joined" event so clients can update in real-time.
    channel = get_events_channel(doctor_id)
    redis.publish(channel, f"patient:{req.patient_id}:joined")

    return {
        "ok": True,
        "patient_id": req.patient_id,
        "doctor_id": doctor_id,
        "newly_added": bool(added),
    }


@router.get("/{doctor_id}", response_model=QueueResponse)
def get_queue(
    doctor_id: int,
    current_user: User = Depends(require_role("admin", "receptionist", "doctor")),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Get the current queue for a doctor (staff and the doctor themselves can view).

    Returns a list of patients in order with their position.
    """

    # Verify the doctor exists.
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    # If the current user is a doctor, they can only view their own queue.
    if current_user.role.value == "doctor" and doctor.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view your own queue")

    # Get all patients in the queue (ZRANGE returns them in score order).
    queue_key = get_queue_key(doctor_id)
    patient_ids = redis.zrange(queue_key, 0, -1)

    items = []
    for idx, patient_id in enumerate(patient_ids):
        # Get the score (timestamp) for the queue position.
        score = redis.zscore(queue_key, patient_id)
        if score is not None:
            since = datetime.utcfromtimestamp(score)
            items.append(
                QueueItemResponse(
                    position=idx + 1,
                    patient_id=int(patient_id),
                    since=since,
                )
            )

    return QueueResponse(
        doctor_id=doctor_id,
        items=items,
        count=len(items),
    )


@router.post("/{doctor_id}/next")
def next_patient(
    doctor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Call the next patient from the queue.

    Atomically removes (and returns) the patient at the head of the queue.
    Only the doctor or staff can do this.
    """

    # Verify the doctor exists.
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    # Check permissions: must be the doctor or staff.
    is_doctor = doctor.user_id == current_user.id
    is_staff = current_user.role.value in ["admin", "receptionist"]

    if not (is_doctor or is_staff):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Pop the first patient from the queue (ZPOPMIN removes and returns).
    queue_key = get_queue_key(doctor_id)
    result = redis.zpopmin(queue_key, 1)

    if not result:
        return {"ok": True, "patient_id": None, "message": "Queue is empty"}

    patient_id_str, score = result[0]
    patient_id = int(patient_id_str)

    # Publish a "called" event so the patient knows they're up.
    channel = get_events_channel(doctor_id)
    redis.publish(channel, f"patient:{patient_id}:called")

    return {
        "ok": True,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
    }
