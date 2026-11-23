# OneCare HMS — Changelog

All notable changes to the OneCare HMS codebase are documented in this file.

---

## [Unreleased] — 2026-11-21

### Added
- **7-Day Trial Lock & Lifecycle Management**:
  - Automatically initializes a 7-day trial period (`trial_started_at` to `trial_expires_at = +7 days`) with a unique UUIDv4 `installation_id` upon initial tenant creation.
  - Added immutable audit trail logging on trial start (`license.trial.started`).
- **Server-Side Anti-Tamper Clock Rollback Detection**:
  - Implemented monotonic epoch timestamp tracking (`last_seen_monotonic_ts`).
  - Detects if system clock is wound back by > 5 minutes (300 seconds); automatically switches license into `RESTRICTED` mode with audit action `license.clock_rollback_detected`.
- **License Enforcement Middleware**:
  - Added `LicenseEnforcementMiddleware` in `backend/licensing/middleware.py`.
  - Blocks operational state-mutating API calls (`POST`, `PUT`, `PATCH`, `DELETE`) with HTTP `403 Forbidden` (`code: LICENSE_RESTRICTED`) when trial or license is expired.
  - Redirects web navigation on protected routes to `/licensing/status/?expired=1` while preserving patient-safe read views and allowing login/logout.
- **1-Year Signed License Key Activation**:
  - Enhanced `activate_signed_license` and licensing providers to support HMAC-SHA256 signed tokens verified against `LICENSE_SIGNING_SECRET` or `LICENSE_PUBLIC_KEY`.
  - Added validation for token expiration (`expires_at`, 365 days default), tenant UUID binding, and installation UUID binding.
  - Unlocks operational features and updates module entitlements on activation with audit log `license.activated`.
- **Standalone Key Generator CLI Tool**:
  - Created `tools/generate_license_key.py` supporting CLI flags (`--secret`, `--days`, `--client-name`, `--tenant-id`, `--installation-id`, `--modules`, and `--verify`).
- **Repository Security & Licensing Guide**:
  - Created `docs/LICENSE_AND_REPO_SECURITY.md` covering cryptographic signing, generation workflows, and a strict GitHub push vs. never-push security checklist.
- **Git Ignore Security**:
  - Added `.gitignore` to protect sensitive local secrets (`.env*`, `*.sqlite3`, `var/`, `tools/license_secrets/`, bytecode, and test caches).
- **Locked Developer Footer & Branding**:
  - Implemented `Developed By - Alok Kumar Kaushal` and `Copyright © 2026` in `backend/core/branding.py` with checksum integrity verification.
  - Injected global `locked_footer()` helper into Jinja2 environment (`backend/config/jinja2_env.py`).
  - Created master layout `backend/jinja2/base.html` and updated templates (`status.html`, `login.html`, `security.html`, `overview.html`, `super_admin.html`, `dashboard.html`).
- **Automated Regression Test Suite**:
  - Added `backend/tests/test_trial_lock_and_activation.py` (6 tests).
  - Added `backend/tests/test_locked_footer.py` (3 tests).
  - All 22 tests across the repository pass cleanly with zero failures.
