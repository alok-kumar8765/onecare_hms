from __future__ import annotations
import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class BaseLicensingProvider:
    def verify_signed_token(self, token: str) -> Optional[dict]:
        raise NotImplementedError


class DevelopmentLicensingProvider(BaseLicensingProvider):
    """
    Isolated development provider: zero external calls.
    Accepts:
    1. Cryptographically signed HMAC-SHA256 tokens (<payload_b64>.<sig_hex>).
    2. Plain base64-encoded JSON payloads for local dev testing without signing secrets.
    """
    def verify_signed_token(self, token: str) -> Optional[dict]:
        if getattr(settings, "DJANGO_ENV", "development") == "production":
            raise ImproperlyConfigured("DevelopmentLicensingProvider cannot run in production.")
        if not token:
            return None

        # Check if this is a signed token (<payload_b64>.<sig_hex>)
        if "." in token:
            secret = (
                getattr(settings, "LICENSE_SIGNING_SECRET", None)
                or getattr(settings, "LICENSE_PUBLIC_KEY", None)
                or "dev-secret-key"
            )
            payload_b64, sig_hex = token.split(".", 1)
            expected_sig = hmac.new(
                secret.encode("utf-8"),
                payload_b64.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(expected_sig, sig_hex.strip()):
                try:
                    padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
                    if "expires_at" in payload:
                        datetime.fromisoformat(payload["expires_at"])
                    return payload
                except Exception:
                    pass

        # Fallback to dev plain base64 json token
        try:
            padded = token + "=" * ((4 - len(token) % 4) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None


class CentralLicensingProvider(BaseLicensingProvider):
    """
    Production license token verifier using HMAC-SHA256 signature verification
    against LICENSE_SIGNING_SECRET or LICENSE_PUBLIC_KEY.
    Format: <base64url_payload>.<hex_hmac_sha256_signature>
    """
    def verify_signed_token(self, token: str) -> Optional[dict]:
        secret = getattr(settings, "LICENSE_SIGNING_SECRET", "") or getattr(settings, "LICENSE_PUBLIC_KEY", "")
        if not secret:
            raise ImproperlyConfigured("LICENSE_SIGNING_SECRET or LICENSE_PUBLIC_KEY must be configured for central licensing.")
        if not token or "." not in token:
            return None
        payload_b64, sig_hex = token.split(".", 1)
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, sig_hex.strip()):
            return None
        try:
            padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
            if "expires_at" in payload:
                datetime.fromisoformat(payload["expires_at"])
            return payload
        except Exception:
            return None


def get_licensing_provider() -> BaseLicensingProvider:
    mode = getattr(settings, "LICENSE_PROVIDER", "development")
    if mode == "development":
        return DevelopmentLicensingProvider()
    return CentralLicensingProvider()
