"""Todo lo que el equipo ve en el admin, con Unfold (iteracion-25 #7 · PLT-B02).

Los modelos de terceros llegan registrados con el ``ModelAdmin`` de Django: sin
volver a registrarlos, sus pantallas salen sin los estilos del admin. Las
sesiones emitidas y las anuladas (lista negra de simplejwt) son las que el
equipo revisa cuando alguien pierde su sesión.
"""

from django.apps import apps
from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

#: Modelos de terceros que el equipo ve en el admin.
AUTH_ADMIN_MODELS = {
    "token_blacklist": ["OutstandingToken", "BlacklistedToken"],
}


def test_every_registered_admin_is_unfold() -> None:
    plain = [
        model._meta.label
        for model, model_admin in admin.site._registry.items()
        if not isinstance(model_admin, UnfoldModelAdmin)
    ]

    assert not plain, "vuelve a registrarlos con un ModelAdmin de Unfold:\n" + (
        "\n".join(plain)
    )


def test_auth_models_are_in_the_admin() -> None:
    missing = [
        f"{label}.{name}"
        for label, names in AUTH_ADMIN_MODELS.items()
        for name in names
        if apps.get_app_config(label).get_model(name) not in admin.site._registry
    ]

    assert not missing, "regístralos con un ModelAdmin de Unfold:\n" + (
        "\n".join(missing)
    )


def test_issued_sessions_stay_read_only_in_the_admin(rf) -> None:
    """Como en simplejwt: una sesión emitida no se crea ni se borra a mano."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    outstanding = admin.site._registry[OutstandingToken]
    request = rf.get("/admin/")

    assert outstanding.has_add_permission(request) is False
    assert outstanding.has_delete_permission(request) is False
    assert outstanding.actions is None
