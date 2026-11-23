from typing import Optional
from tenants.models import Branch


def resolve_scoped_branch_id(
    *,
    tenant_id,
    requested_branch_id=None,
    fallback_branch_id=None,
) -> Optional[object]:
    """
    Validates that a requested or fallback branch belongs to `tenant_id`.
    Returns a verified branch.id or None when no branch is specified.
    Raises ValueError if a branch_id does not exist or belongs to another tenant.
    """
    if not tenant_id:
        return None

    candidate = requested_branch_id if requested_branch_id not in (None, "") else fallback_branch_id
    if candidate in (None, ""):
        return None

    branch = Branch.objects.filter(id=candidate).first()
    if not branch:
        raise ValueError("Selected branch does not exist.")
    if str(branch.tenant_id) != str(tenant_id):
        raise ValueError("Selected branch does not belong to the active organization.")
    return branch.id


def validate_patient_branch_alignment(*, tenant_id, patient, branch_id) -> None:
    """
    Ensures a patient belongs to `tenant_id` and that, if both `patient.branch_id`
    and `branch_id` are set, they do not conflict across branches.
    """
    if not patient:
        return
    if str(patient.tenant_id) != str(tenant_id):
        raise ValueError("Patient does not belong to the active organization.")
    if branch_id and getattr(patient, "branch_id", None) and str(patient.branch_id) != str(branch_id):
        raise ValueError("Patient belongs to a different branch than the selected branch.")