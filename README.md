# EthioClinic: Healthcare Queue & Scheduling System

A production-grade healthcare appointment booking and queue management system built with FastAPI, PostgreSQL, and Redis. Demonstrates a database-level solution to the double-booking race condition.

## What is EthioClinic?

EthioClinic is a REST API for managing patient appointments and queues at a clinic. Patients can book appointments with doctors, check into a queue when they arrive, and the clinic staff can manage the waiting room via Redis-backed queue endpoints. The system includes full authentication (JWT), role-based access control (RBAC), and a PostgreSQL-backed appointment system with a unique constraint that prevents double-booking.

## Tech Stack

- **FastAPI 0.111**: Modern async web framework with automatic OpenAPI docs
- **SQLAlchemy 2.0**: ORM for type-safe database queries
- **PostgreSQL 16**: Relational database with strong constraint enforcement
- **Redis 7**: In-memory data store for high-speed queue operations
- **Pydantic v2**: Request/response validation and serialization
- **passlib + bcrypt**: Secure password hashing
- **python-jose**: JWT token creation and verification
- **pytest + httpx**: Comprehensive test suite

## How to Run

1. **Clone and set up environment:**
   ```bash
   cd ethioclinic
   cp .env.example .env
   ```

2. **Start all services:**
   ```bash
   docker compose up --build
   ```

   The API will be available at `http://localhost:8000`.

3. **View OpenAPI docs:**
   ```
   http://localhost:8000/docs
   ```

4. **Run tests:**
   ```bash
   pip install -r requirements.txt
   pytest -v
   ```

## Demo Script

The following commands demonstrate the full workflow. Run them in order:

### 1. Sign up an admin and a patient
```bash
# Sign up admin
ADMIN_RESP=$(curl -s -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@clinic.com","password":"admin123456"}')
echo "Admin created: $ADMIN_RESP"

# Sign up patient
PATIENT_RESP=$(curl -s -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"patient@clinic.com","password":"patient123456"}')
echo "Patient created: $PATIENT_RESP"
```

### 2. Login both users and capture tokens
```bash
# Admin login
ADMIN_LOGIN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@clinic.com","password":"admin123456"}')
ADMIN_TOKEN=$(echo $ADMIN_LOGIN | jq -r '.access_token')
echo "Admin token: $ADMIN_TOKEN"

# Patient login
PATIENT_LOGIN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"patient@clinic.com","password":"patient123456"}')
PATIENT_TOKEN=$(echo $PATIENT_LOGIN | jq -r '.access_token')
echo "Patient token: $PATIENT_TOKEN"
```

### 3. Admin promotes a user to doctor
```bash
# Create another user for doctor
curl -s -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"doctor@clinic.com","password":"doctor123456"}' | jq .

# Login as doctor to get ID (user_id = 3)
DOCTOR_LOGIN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"doctor@clinic.com","password":"doctor123456"}')
```

### 4. Admin creates a Doctor record
```bash
# Create patient record for patient
curl -s -X POST http://localhost:8000/users/patients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "user_id": 2,
    "full_name": "John Doe",
    "phone": "555-0001",
    "dob": "1990-01-01T00:00:00"
  }' | jq .

# Create doctor record
curl -s -X POST http://localhost:8000/users/doctors \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "user_id": 3,
    "specialty": "General Practice",
    "room_no": "101"
  }' | jq .
```

### 5. Patient books an appointment (should succeed)
```bash
# Patient books an appointment with doctor at doctor_id=1, patient_id=1
SLOT=$(date -u -d "+1 day +10:00" -Iseconds 2>/dev/null || date -u -v+1d -Hh -Mm -Ss 2>/dev/null || echo "2026-04-25T10:00:00")

APPT1=$(curl -s -X POST http://localhost:8000/appointments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  -d "{
    \"doctor_id\": 1,
    \"patient_id\": 1,
    \"slot_at\": \"$SLOT\"
  }")
echo "First appointment (should succeed with 201):"
echo $APPT1 | jq .
```

### 6. Second patient tries the same slot (should get 409)
```bash
# Create and login second patient
curl -s -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"patient2@clinic.com","password":"patient123456"}' | jq .

PATIENT2_LOGIN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"patient2@clinic.com","password":"patient123456"}')
PATIENT2_TOKEN=$(echo $PATIENT2_LOGIN | jq -r '.access_token')

# Create patient2 record
curl -s -X POST http://localhost:8000/users/patients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "user_id": 4,
    "full_name": "Jane Smith",
    "phone": "555-0002"
  }' | jq .

# Try to book the same slot (should fail with 409)
APPT2=$(curl -s -X POST http://localhost:8000/appointments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PATIENT2_TOKEN" \
  -d "{
    \"doctor_id\": 1,
    \"patient_id\": 2,
    \"slot_at\": \"$SLOT\"
  }")
echo "Second appointment (should fail with 409):"
echo $APPT2 | jq .
```

### 7. Patient checks into queue
```bash
curl -s -X POST http://localhost:8000/queue/1/checkin \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  -d '{"patient_id": 1}' | jq .
```

### 8. Staff views queue
```bash
curl -s -X GET http://localhost:8000/queue/1 \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

### 9. Doctor calls next patient
```bash
DOCTOR_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"doctor@clinic.com","password":"doctor123456"}' | jq -r '.access_token')

curl -s -X POST http://localhost:8000/queue/1/next \
  -H "Authorization: Bearer $DOCTOR_TOKEN" | jq .
```

## Running Tests

```bash
# Install test dependencies (already in requirements.txt)
pip install -r requirements.txt

# Run all tests with verbose output
pytest -v

# Run a specific test file
pytest -v tests/test_appointments.py

# Run a specific test
pytest -v tests/test_appointments.py::test_double_booking_is_blocked_by_unique_constraint
```

## The Double-Booking Story: Preventing Race Conditions with Database Constraints

**The Problem:**
Imagine two patients both try to book the same doctor at 3 PM on Monday, milliseconds apart. At the application level, both requests might query the database, see the slot is free, and both insert an appointment. Now we have two appointments for one time slot — a violation of clinic policy.

**The Classic Mistake:**
Many developers try to prevent this with application logic:
```python
if db.query(Appointment).filter(...).first():
    raise "Slot taken"
db.add(new_appointment)
```

This is vulnerable to a race condition. Between the `if` check and the `db.add()`, another request can sneak in.

**The EthioClinic Solution:**
We use a database UNIQUE constraint on the `(doctor_id, slot_at)` columns:

```python
__table_args__ = (
    UniqueConstraint("doctor_id", "slot_at", name="uq_doctor_slot"),
)
```

Now:
1. Request A inserts the first appointment successfully.
2. Request B tries to insert the same (doctor, time) — Postgres atomically rejects it with an IntegrityError.
3. We catch the IntegrityError in our route handler and return HTTP 409 Conflict.

**Why This Works:**
- The database is the source of truth, not the application.
- The database's constraint checking is atomic — no race window.
- If we forget the check in the code, the database still prevents the error.
- The solution scales: multiple servers, async tasks, background jobs — all protected by the same constraint.

**Production Note:**
In a real system, you'd also log these conflicts for analytics (is someone trying to exploit the system?) and offer the patient alternatives (nearby time slots, different doctors, etc.).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Application                       │
├─────────────────────────────────────────────────────────────┤
│  Routes:                                                    │
│  • /auth        – signup, login                             │
│  • /users       – profile, role management                  │
│  • /appointments– book, view, cancel                        │
│  • /queue       – checkin, view, next                       │
├─────────────────────────────────────────────────────────────┤
│ Dependencies:                                               │
│  • JWT authentication (via deps.py)                         │
│  • RBAC (role-based access control)                         │
│  • Database session per request (SQLAlchemy)                │
│  • Redis client for queue operations                        │
└─────────────────────────────────────────────────────────────┘
         ↓                                    ↓
    PostgreSQL 16                         Redis 7
    (Appointments,                       (Queue,
     Users, Doctors,                      Pub/Sub)
     Patients)
```

## Key Design Decisions

1. **JWT over session cookies:** Simpler for mobile and SPAs; no server-side session storage.
2. **Redis sorted sets for queues:** O(log n) insert, O(1) head access, pub/sub for real-time updates.
3. **Constraint-based double-booking prevention:** Database enforces rules, not application code.
4. **Role-based access control:** Every route checks permissions via `require_role()` dependency.
5. **Separate request/response models:** Prevents accidental password leakage.
6. **In-memory SQLite for tests:** Fast, no Docker needed, fully repeatable.

## Security Notes

- Passwords are hashed with bcrypt (cost factor 12, ~150ms per hash).
- JWTs expire after 60 minutes; clients must re-login.
- `JWT_SECRET` defaults to `dev-secret-change-in-production` — change it in production!
- CORS is open (`*`) for the demo — restrict to your front-end domain in production.
- No rate limiting on auth endpoints — add this in production to prevent brute force.

## Future Improvements

- Alembic migrations for schema versioning
- Async Redis (aioredis) for non-blocking queue operations
- Rate limiting and DDoS protection
- Audit logging for all state changes
- Email notifications for appointment reminders
- Multi-tenancy (different clinics on one server)
- Integration with EHR systems

## Contributing

This is a demo project for educational purposes. For production use, see the Security Notes above.
