from django.contrib import messages
from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment
from core.branding import get_locked_footer_html


def environment(**options):
    env = Environment(**options)
    env.globals.update({
        "static": static,
        "url": reverse,
        "get_messages": messages.get_messages,
        "locked_footer": get_locked_footer_html,
    })
    return env
