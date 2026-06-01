# EthioClinic Production Hardening Notes

This file explains what changed to move EthioClinic closer to production and why each change matters.

## 1) Typed Configuration and Secrets

Files:
- `app/config.py`
- `app/db.py`
- `app/redis_client.py`
- `app/security.py`

What changed:
- Added a single typed settings object loaded from env.
- Removed scattered `os.getenv` calls in core modules.
- Added production safety checks (`JWT_SECRET` and CORS validation).

Why it matters:
- Prevents hidden defaults and config drift.
- Makes runtime behavior explicit and testable.
- Fails fast on insecure production startup.

## 2) Migrations Instead of Startup Schema Creation

Files:
- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/0001_initial_schema.py`
- `app/main.py`

What changed:
- Added Alembic migration setup and initial schema migration.
- Removed `Base.metadata.create_all()` from app startup.

Why it matters:
- Schema changes are versioned and reviewable.
- Rollbacks are possible.
- Startup behavior is predictable and safer in production.

## 3) Stronger API Contracts

Files:
- `app/schemas.py`
- `app/routers/users.py`
- `app/routers/appointments.py`

What changed:
- Replaced loose role/status strings with enums.
- Required at least one field for appointment updates.

Why it matters:
- Bad input fails at validation boundary (422) before business logic.
- Reduces runtime edge-case bugs.

## 4) Security and Abuse Controls

Files:
- `app/rate_limit.py`
- `app/routers/auth.py`
- `app/deps.py`

What changed:
- Added auth endpoint rate limiting.
- Added stricter token subject parsing in auth dependency.

Why it matters:
- Slows brute-force and scripted abuse.
- Avoids hidden failures from malformed token claims.

## 5) Observability and Operations

Files:
- `app/logging_config.py`
- `app/middleware.py`
- `app/main.py`

What changed:
- Added request IDs and response header propagation.
- Added request timing/status logging.
- Added `health/live` and `health/ready` endpoints.

Why it matters:
- Easier request tracing in logs.
- Better orchestration health semantics.

## 6) Testing and CI

Files:
- `tests/test_production_hardening.py`
- `.github/workflows/ci.yml`

What changed:
- Added tests for invalid role, invalid token subject, appointment update validation, and queue authorization.
- Added CI workflow to run tests on push/PR.

Why it matters:
- Hardening behavior is continuously enforced.
- Prevents regression as code evolves.

## Suggested Next Improvements

- Move timestamps to timezone-aware UTC (`datetime.now(timezone.utc)`).
- Add audit logs for role changes and sensitive actions.
- Add refresh tokens and token revocation strategy.
- Add Sentry/metrics integration for runtime alerting.
