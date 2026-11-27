# OneCare HMS — Development Status

- **Current Phase:** Phase 6 — Licensing Protection, 7-Day Trial Lock & Developer Branding
- **Completed Tasks:**
  - **7-Day Automatic Trial Initialization**: Generates unique `installation_id` (UUIDv4) upon first tenant start, configures `trial_started_at` to `trial_expires_at = +7 days`, and records immutable audit log `license.trial.started`.
  - **Server-Side Anti-Tamper Clock Rollback Detection**: Monotonic timestamp tracking (`last_seen_monotonic_ts`); trips into `RESTRICTED` mode with audit log `license.clock_rollback_detected` if server clock is wound back by > 5 minutes (300s).
  - **Server-Side License Enforcement Middleware**: `LicenseEnforcementMiddleware` in `backend/licensing/middleware.py` intercepts requests when trial/license is expired:
    - Blocks operational write APIs (`POST`, `PUT`, `PATCH`, `DELETE`) with HTTP `403 Forbidden` (`code: LICENSE_RESTRICTED`).
    - Redirects web navigation to `/licensing/status/?expired=1` while exempting login, logout, static, media, and licensing activation.
  - **1-Year Signed License Key Activation**: Validates HMAC-SHA256 signed tokens via `LICENSE_SIGNING_SECRET` or `LICENSE_PUBLIC_KEY`, verifies expiration (`expires_at` default 365 days), validates tenant and installation ID bindings, unlocks features, updates module entitlements, and records `license.activated` in `AuditLog`.
  - **Standalone License Key Generator & Verifier CLI Tool**: Created `tools/generate_license_key.py` with `--secret`, `--days` (default: 365), `--client-name`, `--tenant-id`, `--installation-id`, `--modules`, and `--verify` options.
  - **Repository & License Security Guide**: Authored `docs/LICENSE_AND_REPO_SECURITY.md` detailing cryptographic key generation, GitHub push vs. never-push checklist, and `.gitignore` audit.
  - **Git Ignore Security Configuration**: Added comprehensive `.gitignore` preventing accidental commits of `.env`, `*.sqlite3`, `var/`, and caches.
  - **Locked Developer Footer**: Implemented `Developed By - Alok Kumar Kaushal` and `Copyright © 2026` with checksum verification helper in `backend/core/branding.py`, Jinja2 global `locked_footer()`, master layout `backend/jinja2/base.html`, and updated all sub-templates.
  - **Automated Test Coverage**: Added `test_trial_lock_and_activation.py` and `test_locked_footer.py`.
- **Confirmed Bugs:** None.
- **Fixed Bugs:** None.
- **Modified / Created Files:**
  - `backend/core/branding.py` (New)
  - `backend/licensing/middleware.py` (New)
  - `tools/generate_license_key.py` (New)
  - `docs/LICENSE_AND_REPO_SECURITY.md` (New)
  - `.gitignore` (New)
  - `backend/tests/test_trial_lock_and_activation.py` (New)
  - `backend/tests/test_locked_footer.py` (New)
  - `backend/config/settings/base.py`
  - `backend/config/jinja2_env.py`
  - `backend/licensing/providers.py`
  - `backend/licensing/services.py`
  - `backend/jinja2/base.html`
  - `backend/jinja2/licensing/status.html`
  - `backend/jinja2/tenants/overview.html`
  - `backend/jinja2/tenants/super_admin.html`
  - `backend/jinja2/accounts/login.html`
  - `backend/jinja2/accounts/security.html`
  - `backend/jinja2/clinic/dashboard.html`
  - `backend/jinja2/pharmacy/dashboard.html`
  - `docs/DEVELOPMENT_STATUS.md`
  - `docs/CHANGELOG.md`
- **Tests Passed:** 22 passed in 24.18s (`pytest backend/tests`).
- **Tests Failed:** 0.
- **Current Blockers:** None.
- **Next Logical Task:** Proceed to remaining planned features or production deployment prep.

# OneCare HMS — Project Status

- **Last Verified Test Run:** `36 passed` in `pytest` (`25.78s`), `manage.py check --settings=config.settings.dev` (`0` issues), `makemigrations --check --dry-run --settings=config.settings.dev` (`No changes detected`).
- **Completed / Verified in Suite:** Multi-tenant & branch scoping, RBAC/2FA/audit logs, licensing & 7-day trial/clock-rollback guards, clinic/OPD, FEFO pharmacy & allergy override, lab verification gate, IPD bed lock/transfer/ledger, GST summary & CSV export, invoice/prescription/lab print HTML views, locked footer, backup/restore CLI & unit/integration coverage.
- **In Progress / Remaining:** Role-gated backup web endpoints (`/core/backup/...`) live browser & Google Drive credential verification, full dashboard/form/CSRF/JS template audit across all Jinja2 templates, and production (`config/settings/prod.py`) + PostgreSQL/MySQL hardening.
