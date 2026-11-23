# OneCare HMS — Platform Owner & Multi-Tenant Setup Guide

## 1. Architecture Mental Model (How Tenants, Branches, Modules & Users Connect)

Unlike a basic single-hospital Django app where you only create `User` accounts:

- **Tenant (`tenant_id` UUID):** Represents one client organization—either a **single standalone clinic** or a **multi-branch hospital network**. Every clinical, pharmacy, and laboratory record is isolated by `tenant_id`.
- **Branch (`branch_id` UUID):** Represents a physical location under a `Tenant` (for example, `MAIN` for headquarters/clinic, `NORTH` or `BLR-02` for additional hospital branches).
- **Module Entitlements (`ModuleEntitlement`):** Controls which modules are active for a `tenant_id` (such as `CLINIC_OPD`, `PHARMACY`, `LABORATORY`, `BILLING`). Modules can be toggled on/off per tenant without reinstalling code.
- **Users (`User.role`, `User.tenant_id`, `User.primary_branch_id`):**
  - `SUPER_ADMIN` (Platform Owner): Manages tenants, module entitlements, licensing, and platform announcements. Usually has `tenant_id = None` when acting at the platform level.
  - `HOSPITAL_OWNER` / `HOSPITAL_ADMIN`: Manages their own organization (`tenant_id`), branches, and staff.
  - `DOCTOR` / `RECEPTIONIST` / `NURSE`: Uses Clinic/OPD/EMR (`/clinic/dashboard/`). Requires `tenant_id` set to their organization.
  - `PHARMACIST`: Uses Pharmacy FEFO inventory & billing (`/pharmacy/dashboard/`). Requires `tenant_id` set to their organization and `PHARMACY` enabled.
  - `LAB_TECHNICIAN` / `LAB_MANAGER`: Uses Laboratory catalog, sample barcodes & verification (`/laboratory/dashboard/`). Requires `tenant_id` set to their organization and `LABORATORY` enabled.

---

## 2. First-Time Local Setup (`setup.bat` or Manual)

### Option A: Run `setup.bat`
Double-click or run from the project root (`one-care-hms`):

```bat
setup.bat