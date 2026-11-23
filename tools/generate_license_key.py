#!/usr/bin/env python3
"""
OneCare HMS — Standalone Cryptographic License Key Generator & Verifier.

Generates and verifies HMAC-SHA256 signed license keys for:
- 1-Year (365 days, configurable) production subscriptions
- Specific tenant or installation UUID hardware/deployment bindings
- Module entitlement grants (CLINIC_OPD, PHARMACY, BILLING, LABORATORY, etc.)

Usage:
    # 1. Generate a 1-year license key for a client:
    python tools/generate_license_key.py --secret "my-super-secure-signing-secret" --client-name "Sunrise Hospital"

    # 2. Generate bound to a specific tenant ID and installation ID:
    python tools/generate_license_key.py --secret "my-secret" --tenant-id "UUID" --installation-id "UUID" --days 365

    # 3. Verify an existing token:
    python tools/generate_license_key.py --secret "my-secret" --verify "<token>"
"""

from __future__ import annotations
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import sys
from typing import Optional, List, Dict, Any

DEFAULT_MODULES = [
    "CLINIC_OPD",
    "BILLING",
    "PHARMACY",
    "LABORATORY",
    "HOSPITAL_IPD",
    "ANALYTICS",
    "HR_PAYROLL",
]


def base64url_encode(data: bytes) -> str:
    """Encodes bytes into URL-safe base64 without trailing padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def base64url_decode(encoded_str: str) -> bytes:
    """Decodes URL-safe base64 string, restoring padding if necessary."""
    padded = encoded_str + "=" * ((4 - len(encoded_str) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def generate_signed_token(
    secret: str,
    payload: Dict[str, Any],
) -> str:
    """
    Serializes payload to canonical JSON, base64url encodes it,
    and computes an HMAC-SHA256 signature against the secret.
    Returns: <base64url_payload>.<signature_hex>
    """
    json_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64url_encode(json_bytes)
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_signed_token(
    secret: str,
    token: str,
) -> Optional[Dict[str, Any]]:
    """
    Verifies the HMAC-SHA256 signature of a token against secret.
    Returns payload dictionary if valid, None otherwise.
    """
    if not token or "." not in token:
        return None

    payload_b64, sig_hex = token.strip().split(".", 1)
    expected_sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_sig, sig_hex.strip()):
        return None

    try:
        raw_json = base64url_decode(payload_b64).decode("utf-8")
        payload = json.loads(raw_json)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="OneCare HMS — License Key Generator & Verifier Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("LICENSE_SIGNING_SECRET") or os.environ.get("LICENSE_PUBLIC_KEY") or "",
        help="Signing secret key (reads LICENSE_SIGNING_SECRET from env by default)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Validity duration in days (default: 365 days / 1 year)",
    )
    parser.add_argument(
        "--client-name",
        default="Licensed Healthcare Facility",
        help="Name of the hospital / clinic licensee",
    )
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Optional Tenant UUID to bind this license to",
    )
    parser.add_argument(
        "--installation-id",
        default=None,
        help="Optional Installation UUID to bind this license to",
    )
    parser.add_argument(
        "--modules",
        default=",".join(DEFAULT_MODULES),
        help=f"Comma-separated module entitlements (default: {','.join(DEFAULT_MODULES)})",
    )
    parser.add_argument(
        "--verify",
        metavar="TOKEN",
        help="Verify an existing signed license key and inspect its claims",
    )

    args = parser.parse_args()

    secret = args.secret.strip()
    if not secret:
        print("ERROR: Signing secret is required.", file=sys.stderr)
        print("Provide via --secret or set LICENSE_SIGNING_SECRET in your environment.", file=sys.stderr)
        sys.exit(1)

    # Verification Mode
    if args.verify:
        token = args.verify.strip()
        print("\n=======================================================")
        print("🔍 OneCare HMS — License Verification")
        print("=======================================================")
        payload = verify_signed_token(secret, token)
        if not payload:
            print("❌ RESULT: INVALID OR TAMPERED TOKEN")
            print("The signature does not match the secret key, or token is malformed.")
            sys.exit(2)

        print("✅ RESULT: SIGNATURE VALID")
        print(f"• Client Name:     {payload.get('client_name', 'N/A')}")
        print(f"• Tenant ID:       {payload.get('tenant_id', 'Any (Unbound)')}")
        print(f"• Installation ID: {payload.get('installation_id', 'Any (Unbound)')}")
        print(f"• Issued At:       {payload.get('issued_at', 'N/A')}")
        print(f"• Expires At:      {payload.get('expires_at', 'N/A')}")

        expires_str = payload.get("expires_at")
        if expires_str:
            try:
                exp_dt = datetime.fromisoformat(expires_str)
                now = datetime.now(timezone.utc)
                if exp_dt < now:
                    print(f"⚠️  WARNING: This license EXPIRED on {exp_dt.isoformat()}.")
                else:
                    days_left = (exp_dt - now).days
                    print(f"• Active Time:     {days_left} days remaining")
            except Exception:
                pass

        modules = payload.get("modules", [])
        print(f"• Licensed Modules: {', '.join(modules) if modules else 'All'}")
        print("=======================================================\n")
        return

    # Generation Mode
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=args.days)
    modules_list = [m.strip().upper() for m in args.modules.split(",") if m.strip()]

    payload = {
        "client_name": args.client_name,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "modules": modules_list,
    }
    if args.tenant_id:
        payload["tenant_id"] = args.tenant_id.strip()
    if args.installation_id:
        payload["installation_id"] = args.installation_id.strip()

    token = generate_signed_token(secret, payload)

    print("\n=======================================================")
    print("🔑 OneCare HMS — Signed 1-Year License Key Generated")
    print("=======================================================")
    print(f"• Client:          {args.client_name}")
    print(f"• Tenant ID:       {payload.get('tenant_id', 'Any / Unbound')}")
    print(f"• Installation ID: {payload.get('installation_id', 'Any / Unbound')}")
    print(f"• Issued Date:     {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"• Expiry Date:     {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')} ({args.days} days)")
    print(f"• Entitlements:    {', '.join(modules_list)}")
    print("-------------------------------------------------------")
    print("SIGNED LICENSE TOKEN (Copy everything below):")
    print(token)
    print("-------------------------------------------------------")
    print("ACTIVATION INSTRUCTIONS:")
    print("1. Web Interface:")
    print("   Navigate to: http://<your-host>/licensing/status/")
    print("   Paste the token into the 'Activate License' box and click Activate.")
    print("2. REST API:")
    print("   curl -X POST http://<your-host>/api/v1/licensing/activate/ \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -H 'Authorization: Bearer <ADMIN_TOKEN>' \\")
    print(f"     -d '{{\"signed_token\": \"{token}\"}}'")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
