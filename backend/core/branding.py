from __future__ import annotations
import hashlib

DEVELOPER_NAME = "Alok Kumar Kaushal"
COPYRIGHT_YEAR = "2026"
CANONICAL_BRANDING = f"Developed By - {DEVELOPER_NAME} | Copyright © {COPYRIGHT_YEAR}"


def verify_branding_integrity() -> bool:
    """
    Verifies that the developer branding and copyright year have not been altered.
    """
    return DEVELOPER_NAME == "Alok Kumar Kaushal" and COPYRIGHT_YEAR == "2026"


def get_locked_footer_html() -> str:
    """
    Returns the protected, tamper-resistant developer footer markup.
    Renders 'Developed By - Alok Kumar Kaushal' and 'Copyright © 2026'.
    """
    if not verify_branding_integrity():
        dev = "Alok Kumar Kaushal"
        year = "2026"
    else:
        dev = DEVELOPER_NAME
        year = COPYRIGHT_YEAR

    return (
        f'<footer class="w-full border-t border-slate-800 bg-slate-950/80 py-4 px-6 text-center text-xs text-slate-400 mt-auto">\n'
        f'  <div class="flex flex-col sm:flex-row items-center justify-between max-w-6xl mx-auto gap-2">\n'
        f'    <span>OneCare HMS &bull; Enterprise Hospital Management System</span>\n'
        f'    <span class="font-medium text-slate-300">Developed By - {dev} | Copyright &copy; {year}</span>\n'
        f'  </div>\n'
        f'</footer>'
    )
