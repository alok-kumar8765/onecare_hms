# OneCare HMS — Licensing Architecture & Repository Security Guide

> **Author**: Alok Kumar Kaushal  
> **Applicable Version**: OneCare HMS v1.0.0+  
> **Last Updated**: November 2026  

---

## 1. Executive Summary & Architecture

OneCare HMS implements a **Server-Side 7-Day Trial Lock and 1-Year Signed License Key Activation System** designed to protect intellectual property in self-hosted on-premise and private cloud hospital deployments while preserving critical medical record data integrity.

### Core Architectural Principles:
1. **7-Day Automatic Trial**:
   - When a tenant or installation is provisioned for the first time, a unique `installation_id` (UUIDv4) is generated.
   - A 7-day trial period (`trial_started_at` to `trial_expires_at = +7 days`) is initiated and recorded in the database.
   - An immutable audit log entry (`license.trial.started`) is created.
2. **Patient-Data-Safe Restricted Mode (Trial / License Expiration)**:
   - When the 7-day trial expires without an active signed license key, or when an active 1-year license reaches its `license_expires_at` date:
     - The application enters **Restricted Mode**.
     - **Operational state-mutating API calls (`POST`, `PUT`, `PATCH`, `DELETE`)** are blocked with HTTP `403 Forbidden` (`code: LICENSE_RESTRICTED`).
     - **Web UI navigation** redirects the user to the License Activation screen (`/licensing/status/?expired=1`).
     - **Critical Patient Safety**: In emergency healthcare scenarios, doctors and staff can still view existing patient EMRs, lab reports, and prescriptions (read-only `GET`/`HEAD`/`OPTIONS` requests) so patient life is never endangered.
3. **Server-Side Anti-Tamper & Clock Rollback Detection**:
   - The backend tracks a monotonic timestamp (`last_seen_monotonic_ts`) on every verified request.
   - If an administrator rolls back the server's system clock by more than 5 minutes (300 seconds) to bypass trial expiration, the system instantly detects the anomaly, triggers an audit event (`license.clock_rollback_detected`), and locks the workspace into Restricted Mode.
   - License validation is enforced strictly server-side inside Django middleware and DRF permission classes; client-side JavaScript or localStorage cannot bypass this gate.
4. **1-Year Signed License Key Activation**:
   - The license key is an offline-verifiable cryptographically signed token signed with HMAC-SHA256:
     ```text
     <base64url_json_payload>.<hmac_sha256_hex_signature>
     ```
   - The payload contains:
     - `client_name`: Name of hospital or clinic.
     - `issued_at`: UTC ISO-8601 issuance timestamp.
     - `expires_at`: UTC ISO-8601 expiration timestamp (default: 365 days / 1 year from issue).
     - `modules`: List of enabled module entitlements (e.g. `CLINIC_OPD`, `BILLING`, `PHARMACY`, etc.).
     - `tenant_id` *(Optional)*: Locks the license to a specific tenant UUID.
     - `installation_id` *(Optional)*: Locks the license to a specific installation deployment UUID.
   - When entered via web (`/licensing/status/`) or API (`/api/v1/licensing/activate/`), the backend verifies the signature, validates expiration and hardware/tenant bindings, restores `ACTIVE` status, and logs `license.activated` in `AuditLog`.

---

## 2. Generating 1-Year Signed License Keys

A standalone, dependency-free license key generator tool is located at:
```text
tools/generate_license_key.py
```

### Step-by-Step Generation Workflow:

1. **Keep the signing secret secure on your vendor machine**:
   Set `LICENSE_SIGNING_SECRET` in your local environment or pass it to the script via `--secret`.

2. **Generate a 1-year key for a hospital**:
   ```bash
   python tools/generate_license_key.py \
       --secret "your-private-licensing-master-secret" \
       --client-name "Apollo Life Hospital" \
       --days 365
   ```

3. **Generate a key bound to a specific Tenant and Installation**:
   ```bash
   python tools/generate_license_key.py \
       --secret "your-private-licensing-master-secret" \
       --client-name "Sunrise Clinic" \
       --tenant-id "a3bb189e-8bf9-4888-9912-ace4e6543002" \
       --installation-id "f47ac10b-58cc-4372-a567-0e02b2c3d479" \
       --days 365 \
       --modules "CLINIC_OPD,BILLING,PHARMACY"
   ```

4. **Verify an existing key**:
   ```bash
   python tools/generate_license_key.py \
       --secret "your-private-licensing-master-secret" \
       --verify "<token>"
   ```

---

## 3. GitHub Push & Repository Protection Checklist

When publishing this repository to GitHub or delivering source packages to clients, follow this mandatory checklist to protect sensitive keys and proprietary assets.

### 🔴 WHAT MUST NEVER BE PUSHED TO GITHUB OR SHIPPED TO CLIENTS:

| Item | Reason |
| :--- | :--- |
| **`LICENSE_SIGNING_SECRET`** | The private master secret used to sign license keys. If leaked, clients can generate unlimited free keys. Must only exist on your private machine. |
| **Production `.env`** | Contains production database passwords, Django `SECRET_KEY`, and API secrets. |
| **Local SQLite databases (`*.sqlite3`, `db.sqlite3`)** | Contains local development patient data, test users, and installation IDs. |
| **Runtime storage (`var/`, `media/`, `backups/`)** | Contains uploaded patient photos, diagnostic scans, and automated DB backups. |
| **Bytecode & caches (`__pycache__/`, `*.pyc`, `.pytest_cache/`)** | Intermediate compiled files that cause environment conflicts. |
| **Private key generator secrets (`tools/license_secrets/`)** | Any private key files or generator scripts with hardcoded secrets. |

### 🟢 WHAT MUST BE PUSHED TO GITHUB:

| Item | Purpose |
| :--- | :--- |
| **Clean source code (`backend/`)** | Full Django application, views, models, services, forms. |
| **Schema migrations (`*/migrations/000*.py`)** | Reproducible database schema definitions. |
| **Automated test suite (`backend/tests/`)** | Regression testing with pytest. |
| **`.env.example`** | Safe template showing all environment variables with empty/dummy values. |
| **`.gitignore`** | Configured to block `.env`, `db.sqlite3`, `var/`, and cache directories. |
| **Documentation (`docs/`)** | Architecture, security, API references, and deployment guides. |

---

## 4. Locked Footer & Branding Protection

### Developer Signature:
```text
Developed By - Alok Kumar Kaushal | Copyright © 2026
```

### Tamper-Resistance Design:
- Defined in `backend/core/branding.py`.
- Includes a checksum integrity verification helper (`verify_branding_integrity()`).
- Injected globally into the Jinja2 template engine via `config/jinja2_env.py` (`locked_footer()`).
- Included across shared base templates (`base.html`), authentication pages (`login.html`, `security.html`), tenant views (`overview.html`, `super_admin.html`), clinic workspaces (`dashboard.html`), and licensing consoles (`status.html`).
- Automated regression tests in `backend/tests/test_locked_footer.py` assert that both `Developed By - Alok Kumar Kaushal` and `Copyright © 2026` are strictly present in rendered responses.

### Self-Hosted Deployment Considerations:
In self-hosted Python deployments, clients have physical access to source files on their server. While code obfuscation (such as PyArmor or Cython) can add compilation barriers, server-side cryptographic enforcement of license validity and immutable audit logging provide the true operational security perimeter.
