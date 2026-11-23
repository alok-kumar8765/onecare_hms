# OneCare HMS — Project Master

- **Product:** OneCare HMS (Modular Multi-Tenant Healthcare Management SaaS)
- **Primary Market:** India (INR/GST workflows, ABDM/FHIR/DPDP readiness without unverified compliance claims)
- **Supported Deployment Modes:**
  1. Full Hospital Management
  2. Standalone Clinic Management
  3. Clinic + Laboratory
  4. Clinic + Pharmacy
  5. Standalone Pharmacy
  6. Standalone Laboratory
- **Web Stack:** Jinja2 templates + Tailwind CSS + Alpine.js + Chart.js
- **API Stack:** Django REST Framework (per-module `api.py` under `/api/v1/`) sharing `services.py` with Jinja2 views
- **Dev Strategy:** SQLite3, local file storage, mock providers (SMS, Email, WhatsApp, Payments, AI), and isolated `DEVELOPMENT` licensing provider (zero mandatory paid APIs during development)
- **Prod Strategy:** PostgreSQL, S3-compatible storage, real providers/webhooks, strict env validation (no dev bypass in production), HTTPS, and tested backups/restores
- **Licensing & Data Rule:** 7-day trial -> valid license/entitlements -> Patient-Data-Safe Restricted Mode on expiry (blocks new operational writes/unlicensed modules; preserves patient records, authorized exports, backups, audit logs, and renewal flow)
- **Current Phase:** Phase 1 — Project Foundation (In Progress)