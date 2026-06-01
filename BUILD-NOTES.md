# EthioClinic Build Notes

## File Tree

```
ethioclinic/
├── README.md                    # Full documentation + demo script
├── BUILD-NOTES.md               # This file
├── requirements.txt             # Python dependencies (pinned versions)
├── docker-compose.yml           # Docker Compose with postgres, redis, api
├── Dockerfile                   # Multi-stage build for the FastAPI app
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules
│
├── app/
│   ├── __init__.py              # Package marker
│   ├── main.py                  # FastAPI app, startup, health check, router mounting
│   ├── db.py                    # SQLAlchemy engine, session factory
│   ├── redis_client.py          # Redis client singleton
│   ├── models.py                # User, Role, Patient, Doctor, Appointment (+ UNIQUE constraint)
│   ├── schemas.py               # Pydantic request/response models
│   ├── security.py              # Password hashing (bcrypt) + JWT token utils
│   ├── deps.py                  # Dependency injection: get_current_user, require_role
│   └── routers/
│       ├── __init__.py
│       ├── auth.py              # POST /auth/signup, POST /auth/login
│       ├── users.py             # GET /users/me, PATCH /users/{id}/role, POST /users/patients, POST /users/doctors
│       ├── appointments.py       # POST /appointments (WITH IntegrityError handler), GET, PATCH, list
│       └── queue.py             # POST /queue/{doctor_id}/checkin, GET queue, POST next
│
└── tests/
    ├── __init__.py
    ├── conftest.py              # Fixtures: in-memory SQLite, fakeredis, TestClient
    ├── test_auth.py             # Signup, login, duplicate email, wrong password
    ├── test_appointments.py      # CRITICAL: test_double_booking_is_blocked_by_unique_constraint
    └── test_queue.py            # Checkin, idempotent, list, next
```

## Key Design Decisions

### 1. UNIQUE Constraint on Appointments (The Headline Story)
- **Why:** Prevents double-booking at the database level, not the application.
- **How:** `Appointment.__table_args__ = (UniqueConstraint("doctor_id", "slot_at"),)`
- **Benefit:** Atomic, no race window, works across multiple servers/processes.
- **Where:** See `app/models.py` (heavy comment block) and `app/routers/appointments.py` (try/except IntegrityError).

### 2. JWT Authentication
- **Secret:** From `JWT_SECRET` env var, defaults to `dev-secret-change-in-production`.
- **Expiry:** 60 minutes (hardcoded in `app/security.py`).
- **Algorithm:** HS256 (symmetric, suitable for a backend signing its own tokens).
- **Payload:** `{sub: user_id, role, exp}`.

### 3. RBAC via `require_role()` Dependency
- **Pattern:** `@app.get("/admin", Depends(require_role("admin")))` auto-checks permission.
- **Advantage:** No boilerplate in route handlers; single source of truth for auth.
- **Alternative:** Could use Fastapi-Permissions or similar; this is simpler for learning.

### 4. Redis for Queue Operations
- **Key Pattern:** `queue:doctor:{doctor_id}` → a Redis sorted set.
- **Score:** Enqueue timestamp (UNIX epoch), so we can track "since when" and maintain order.
- **Operations:**
  - `ZADD` (idempotent with NX flag) for checkin.
  - `ZRANGE` for listing.
  - `ZPOPMIN` for calling next (atomic pop from head).
- **Why Sorted Sets:** O(log n) insert, O(1) head access, natural ordering.

### 5. Test Strategy
- **In-Memory SQLite:** No Postgres setup needed, instant.
- **Fakeredis:** In-memory Redis, no network calls.
- **Fixtures for Auth:** `auth_headers` and `admin_headers` provide pre-signed JWTs.
- **Critical Test:** `test_double_booking_is_blocked_by_unique_constraint` verifies the headline story.

### 6. Separation of Concerns
- **models.py:** ORM definitions only.
- **schemas.py:** Pydantic I/O models (never include passwords in responses).
- **security.py:** Password hashing + JWT logic (no routes here).
- **deps.py:** FastAPI dependencies (auth, RBAC).
- **routers/*.py:** HTTP handlers (slim, just business logic).

### 7. Error Handling
- **IntegrityError:** Caught in `/appointments` POST to return 409 (double-booking).
- **404:** Explicit queries with `.first()` and `HTTPException(status_code=404)`.
- **403:** `require_role()` raises 403 if user doesn't have permission.
- **401:** `get_current_user()` raises 401 on bad/missing token.

### 8. CORS Open for Demo
- **Why:** Allows curl/postman from any origin.
- **Production:** Restrict to your front-end domain only.

## Commands to Bring It Up and Demo

### Prerequisites
- Docker and Docker Compose installed.
- `curl` and `jq` for the demo script (or use Postman).

### Start the System

```bash
cd ethioclinic
cp .env.example .env
docker compose up --build
```

Wait for all three services to report healthy:
```
ethioclinic-db ... healthy
ethioclinic-redis ... healthy
ethioclinic-api ... ready
```

### Quick Health Check
```bash
curl http://localhost:8000/health
# Should return: {"ok":true,"db":"up","redis":"up"}
```

### Run the Full Demo

1. **Sign up and login users** (captures tokens):
   ```bash
   # Admin signup
   curl -s -X POST http://localhost:8000/auth/signup \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@clinic.com","password":"admin123456"}' | jq .

   # Admin login (capture token)
   ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@clinic.com","password":"admin123456"}' | jq -r '.access_token')
   echo "Admin Token: $ADMIN_TOKEN"
   ```

2. **Create doctor and patients:**
   See the full demo script in README.md (section "Demo Script").

3. **The Money Shot — Double-booking Prevention:**
   ```bash
   # Patient 1 books slot at 10 AM
   curl -s -X POST http://localhost:8000/appointments \
     -H "Authorization: Bearer $PATIENT1_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "doctor_id": 1,
       "patient_id": 1,
       "slot_at": "2026-04-25T10:00:00"
     }' | jq .
   # Returns 201 ✓

   # Patient 2 tries the same slot
   curl -s -X POST http://localhost:8000/appointments \
     -H "Authorization: Bearer $PATIENT2_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "doctor_id": 1,
       "patient_id": 2,
       "slot_at": "2026-04-25T10:00:00"
     }' | jq .
   # Returns 409 with detail: "This time slot is already booked" ✓
   ```

   This is the headline story: the database rejected the duplicate because of the UNIQUE constraint.

### Run Tests

```bash
pip install -r requirements.txt
pytest -v

# Or just the critical test:
pytest -v tests/test_appointments.py::test_double_booking_is_blocked_by_unique_constraint
```

Expected output:
```
test_auth.py::test_signup PASSED
test_auth.py::test_login PASSED
test_appointments.py::test_double_booking_is_blocked_by_unique_constraint PASSED
test_queue.py::test_checkin_success PASSED
...
```

## Caveats and Notes

1. **Postgres Startup Time:** On first `docker compose up`, Postgres may take 5-10 seconds to initialize. The `depends_on` with `condition: service_healthy` ensures the API waits.

2. **Environment Variables:** The `.env` file is not tracked in git (see `.gitignore`). Always use `.env.example` as a template. In production, secrets come from a vault (e.g., Hashicorp Vault, AWS Secrets Manager).

3. **JWT Secret:** The default `JWT_SECRET` in `.env.example` is `dev-secret-change-in-production`. Change it to a long random string in any real environment. If you don't, tokens are predictable.

4. **Database Migrations:** We use `Base.metadata.create_all()` on startup (good for demos, not for production). In production, use Alembic for versioned, reversible migrations.

5. **Password Hashing Cost:** We use bcrypt with the default cost factor (12). Each hash takes ~150ms. This is intentional (slows down brute force) but can be noticeable in tests. If tests are too slow, reduce the factor in conftest.py.

6. **Redis Persistence:** By default, Redis is in-memory only (no AOF/RDB). This means if the container crashes, the queue is lost. For production, enable Redis persistence or use a managed Redis service.

7. **Async vs Sync:** We use sync Redis and sync database drivers. This is fine for a demo but not optimal for high concurrency. Production would use async (aioredis, asyncpg).

8. **CORS:** Currently allows all origins (`allow_origins=["*"]`). Restrict this in production to your front-end domain.

9. **No Rate Limiting:** The auth endpoints don't rate-limit login attempts. Add this in production (e.g., `slowapi` or `limits` library).

10. **Test Database:** Tests use an in-memory SQLite database, which is fast but has subtle differences from Postgres (e.g., no UUID type, different UNIQUE constraint behavior). For critical tests, also run against a real Postgres.

## Interview Talking Points

When Segni demos this at Abbott, here are the key points to emphasize:

1. **The UNIQUE Constraint Solution:** Why it's better than application-level checks. Show the code in `models.py` and the try/except in `appointments.py`.

2. **Database Enforces Policy:** The database is the source of truth. Even if the application code forgets the check, Postgres enforces it.

3. **No Race Condition:** Unlike check-then-insert, the constraint is atomic. No window where two requests can both succeed.

4. **Clean Error Handling:** We catch `IntegrityError` and return HTTP 409, a clean contract with the client.

5. **Test Coverage:** The critical test (`test_double_booking_is_blocked_by_unique_constraint`) proves it works. Run it during the demo.

6. **Production-Ready Patterns:**
   - JWT auth with expiry
   - RBAC via dependency injection
   - Separate request/response models
   - Comprehensive error handling
   - Full test suite

7. **Learning Value:** The codebase is heavily commented in a conversational style. Every design decision is explained. Ideal for onboarding new engineers.

## File Size Reference

- `main.py`: ~80 lines (clean, just routing)
- `appointments.py`: ~180 lines (long comments on IntegrityError handling)
- `security.py`: ~60 lines
- `models.py`: ~150 lines
- `schemas.py`: ~130 lines
- `deps.py`: ~90 lines

Total app code: ~1000 lines (including comments and docstrings).

## Common Troubleshooting

### "Connection refused" when api starts
→ Postgres is still initializing. Docker Compose's `depends_on` with `service_healthy` should handle this. If not, wait 10 seconds and retry.

### "UNIQUE constraint violated" when running tests
→ Likely a test isolation issue. Check that `conftest.py` is correctly rolling back transactions between tests.

### "redis-cli: command not found"
→ Use Docker to run redis-cli: `docker exec ethioclinic-redis redis-cli ping`

### JWTs expire too fast (60 minutes)
→ Change `JWT_EXPIRY_MINUTES` in `security.py`. For the demo, you might want 24 hours.

### Can't connect to localhost:5432 from host machine
→ Port is only exposed when running via Docker Compose. To query Postgres directly:
```bash
docker exec ethioclinic-db psql -U postgres -d ethioclinic -c "SELECT * FROM users;"
```
