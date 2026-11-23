from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from .models import UserDevice, UserRole
from .services import approve_user_device, evaluate_login_attempt, issue_whatsapp_otp, verify_totp_code


def get_default_home_url_name(user) -> str:
    role = getattr(user, "role", None)
    if role == UserRole.SUPER_ADMIN:
        return "tenants-super-admin"
    if role == UserRole.PHARMACIST:
        return "pharmacy-dashboard"
    if role in {UserRole.LAB_TECHNICIAN, UserRole.LAB_MANAGER}:
        return "laboratory-dashboard"
    if role in {UserRole.DOCTOR, UserRole.RECEPTIONIST, UserRole.NURSE}:
        return "clinic-dashboard"
    return "tenants-overview"

def login_view(request):
    context = {"error": None, "require_2fa": False, "pending_username": "", "new_device_alert": False}
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        totp_code = (request.POST.get("totp_code") or "").strip()
        ip = request.META.get("REMOTE_ADDR")
        ua = request.META.get("HTTP_USER_AGENT", "")

        result = evaluate_login_attempt(
            username=username,
            password=password,
            user_agent=ua,
            ip_address=ip,
            request=request,
        )
        if not result["ok"]:
            context["error"] = result["message"]
            return render(request, "accounts/login.html", context)

        user = result["user"]
        if result["requires_2fa"]:
            if not totp_code:
                context["require_2fa"] = True
                context["pending_username"] = username
                context["new_device_alert"] = result["new_device_alert"]
                context["error"] = "Enter your 6-digit authenticator code to complete sign-in."
                return render(request, "accounts/login.html", context)
            if not verify_totp_code(user.totp_secret, totp_code):
                context["require_2fa"] = True
                context["pending_username"] = username
                context["new_device_alert"] = result["new_device_alert"]
                context["error"] = "Invalid 2FA code. Please try again."
                return render(request, "accounts/login.html", context)

        auth_login(request, user)
        if user.tenant_id:
            request.session["active_tenant_id"] = str(user.tenant_id)
        if user.primary_branch_id:
            request.session["active_branch_id"] = str(user.primary_branch_id)
        return redirect(get_default_home_url_name(user))

    return render(request, "accounts/login.html", context)


@login_required
def logout_view(request):
    auth_logout(request)
    return redirect("accounts-login")


@login_required
def security_view(request):
    totp_secret = request.user.ensure_totp_secret()
    devices = UserDevice.objects.filter(user=request.user).order_by("-last_seen_at")
    mock_otp_preview = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "enable_totp":
            code = (request.POST.get("totp_code") or "").strip()
            if verify_totp_code(totp_secret, code):
                request.user.two_factor_enabled = True
                request.user.totp_verified = True
                request.user.save(update_fields=["two_factor_enabled", "totp_verified"])
        elif action == "approve_device":
            device_id = request.POST.get("device_id")
            approve_user_device(user=request.user, device_id=device_id, request=request)
        elif action == "send_mock_whatsapp_otp":
            _, otp_code = issue_whatsapp_otp(request.user, request=request, provider_mode="mock")
            mock_otp_preview = otp_code

    return render(
        request,
        "accounts/security.html",
        {
            "user_obj": request.user,
            "totp_secret": totp_secret,
            "devices": devices,
            "mock_otp_preview": mock_otp_preview,
        },
    )