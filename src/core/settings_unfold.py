"""Django Unfold admin configuration (iteracion-13; paleta de piedra, iteracion-20)."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _

UNFOLD = {
    "SITE_TITLE": _("Itzaka Admin"),
    "SITE_HEADER": _("Itzaka"),
    # Un callable: settings_unfold no puede importar APP_VERSION (circular);
    # templates/admin/login.html lo repite en el acceso.
    "SITE_SUBHEADER": lambda request: f"v{settings.APP_VERSION}",
    "SITE_URL": "/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    # Manual de marca v2.0: obsidiana como primario y neutrales de piedra y cal
    # (los grises azulados de Unfold no son de la marca).
    "COLORS": {
        "base": {
            "50": "#FAF9F7",
            "100": "#F5F3F0",
            "200": "#ECE9E4",
            "300": "#E4E0DA",
            "400": "#ADA79F",
            "500": "#8C857C",
            "600": "#5E5A55",
            "700": "#3A3733",
            "800": "#26262A",
            "900": "#1C1D20",
            "950": "#141517",
        },
        "primary": {
            "50": "#F5F4F2",
            "100": "#E8E7E5",
            "200": "#CFCDCA",
            "300": "#9C9A97",
            "400": "#77777B",
            "500": "#55565B",
            "600": "#2B2C30",
            "700": "#1F2023",
            "800": "#141517",
            "900": "#0C0D0E",
            "950": "#070708",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
}
