"""Platform baseline: Unfold admin + WhiteNoise (TDD-B01, iteracion-13 #1).

Not tied to a user story. The registry test keeps going RED whenever a model is
added without its Unfold admin.
"""

import pytest
from django.apps import apps
from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

# Models deliberately kept out of the admin. Every entry needs a justification.
EXCLUDED_FROM_ADMIN: set[str] = set()


def _local_models():
    return [
        model
        for model in apps.get_models()
        if model.__module__.startswith("apps.")
        and model._meta.label not in EXCLUDED_FROM_ADMIN
    ]


def test_unfold_is_installed_before_django_admin(settings):
    installed = list(settings.INSTALLED_APPS)
    assert "unfold" in installed
    assert installed.index("unfold") < installed.index("django.contrib.admin")


def test_whitenoise_middleware_follows_security_middleware(settings):
    middleware = list(settings.MIDDLEWARE)
    security = middleware.index("django.middleware.security.SecurityMiddleware")
    assert middleware[security + 1] == "whitenoise.middleware.WhiteNoiseMiddleware"


@pytest.mark.django_db
def test_admin_login_page_renders_with_unfold_templates(client):
    response = client.get("/admin/login/")
    assert response.status_code == 200
    assert any(t.origin and "unfold" in t.origin.name for t in response.templates)


@pytest.mark.django_db
def test_admin_login_lands_on_the_admin(client, django_user_model):
    """Unfold's login form posts no ``next``: it must not end in a 404."""
    django_user_model.objects.create_superuser(
        email="admin@cuotreka.test", password="Tejado-Admin-81"
    )

    response = client.post(
        "/admin/login/",
        {"username": "admin@cuotreka.test", "password": "Tejado-Admin-81"},
    )

    assert response.status_code == 302
    assert response["Location"] == "/admin/"


@pytest.mark.parametrize("model", _local_models(), ids=lambda m: m._meta.label)
def test_local_model_is_registered_with_unfold_model_admin(model):
    model_admin = admin.site._registry.get(model)
    assert model_admin is not None, f"{model._meta.label} is not in the admin"
    assert isinstance(model_admin, UnfoldModelAdmin), (
        f"{model._meta.label} uses {type(model_admin).__name__}, not Unfold's"
    )
