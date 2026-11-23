from typing import Optional
from .models import AuditLog
import ipaddress
from typing import Optional, Set
from django.conf import settings

def _parse_trusted_proxies() -> Set[str]:
    raw = getattr(settings, "TRUSTED_PROXY_IPS", None)
    if not raw:
        return set()
    if isinstance(raw, str):
        return {item.strip() for item in raw.split(",") if item.strip()}
    return {str(item).strip() for item in raw if str(item).strip()}


def _is_valid_ip(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate.strip())
        return True
    except ValueError:
        return False


def _get_client_ip(request) -> Optional[str]:
    """
    Extracts the client IP safely. Only trusts X-Forwarded-For when REMOTE_ADDR
    is explicitly listed in settings.TRUSTED_PROXY_IPS; otherwise falls back to REMOTE_ADDR.
    """
    if request is None or not hasattr(request, "META"):
        return None

    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    trusted_proxies = _parse_trusted_proxies()

    if remote_addr and remote_addr in trusted_proxies:
        xff = request.META.get("HTTP_X_FORWARDED_FOR") or ""
        hops = [hop.strip() for hop in xff.split(",") if hop.strip()]
        # Walk backwards through hops, skipping any known trusted proxies
        for hop in reversed(hops):
            if _is_valid_ip(hop) and hop not in trusted_proxies:
                return hop

    return remote_addr if _is_valid_ip(remote_addr) else None


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