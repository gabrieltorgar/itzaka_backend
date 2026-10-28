"""Django Unfold admin configuration (iteracion-13)."""

from django.utils.translation import gettext_lazy as _

UNFOLD = {
    "SITE_TITLE": _("Itzaka Admin"),
    "SITE_HEADER": _("Itzaka"),
    "SITE_URL": "/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
}
