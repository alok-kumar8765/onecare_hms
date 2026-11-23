# backend/licensing/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .services import activate_signed_license, get_or_start_installation_license


@login_required
def license_status_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)
    lic = get_or_start_installation_license(tenant_id=tenant_id, request=request) if tenant_id else None
    feedback = None
    ok = None

    if request.method == "POST" and tenant_id:
        token = (request.POST.get("signed_token") or "").strip()
        ok, feedback, lic = activate_signed_license(
            tenant_id=tenant_id,
            signed_token=token,
            actor=request.user,
            request=request,
        )

    return render(
        request,
        "licensing/status.html",
        {"license": lic, "feedback": feedback, "ok": ok},
    )