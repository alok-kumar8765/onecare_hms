# OneCare HMS — Architecture

- **Multi-Tenancy:** Shared schema with mandatory `tenant_id` (and `branch_id` for branch-scoped entities). Tenant and branch context are resolved server-side from authenticated session/token state—never trusted from raw client payload IDs.
- **Layering per Module:**
  - `models.py` — Tenant/branch-scoped data models
  - `services.py` — Core transactional/business logic shared by web and mobile APIs
  - `serializers.py` & `api.py` — DRF REST endpoints for Android/iOS/external clients
  - `views.py` & `jinja2/...` — Server-rendered Jinja2 UI with Tailwind CSS & Alpine.js
- **Security & Audit:** Argon2id/PBKDF2 password hashing, rate limiting, session/token security, 2FA (TOTP + new-device login alerts + dev/prod WhatsApp OTP), granular RBAC, and `AuditLog` entries for sensitive operations.
- **Data Portability:** Filterable import/export (previous year, current year, month, custom date range, doctor, branch/module) with dry-run validation and duplicate checks.