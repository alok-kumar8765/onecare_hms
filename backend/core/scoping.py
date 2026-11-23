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
    Returns a verified branch.id or None if no branch is specified.
    Raises ValueError if a branch_id exists under a different tenant or is invalid.
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