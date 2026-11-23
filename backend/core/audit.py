from typing import Optional
from .models import AuditLog


def _get_client_ip(request):
    if not request:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_audit_log(
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    actor=None,
    tenant_id=None,
    branch_id=None,
    request=None,
    metadata: Optional[dict] = None,
) -> AuditLog:
    resolved_actor = actor if actor is not None else getattr(request, "user", None)
    if resolved_actor is not None and not getattr(resolved_actor, "is_authenticated", False):
        resolved_actor = None

    resolved_tenant = tenant_id or getattr(request, "active_tenant_id", None) or getattr(resolved_actor, "tenant_id", None)
    resolved_branch = branch_id or getattr(request, "active_branch_id", None)

    return AuditLog.objects.create(
        tenant_id=resolved_tenant,
        branch_id=resolved_branch,
        actor=resolved_actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        ip_address=_get_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
        metadata=metadata or {},
    )