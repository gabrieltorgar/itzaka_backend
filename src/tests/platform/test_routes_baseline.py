"""Línea base de rutas: quién entra sin sesión y con qué límite (TDD-B01).

No sale de una historia (iteracion-25 #10): toda ruta de la API pide sesión
salvo las de la lista blanca de abajo, cada una con su motivo. Una vista nueva
que se abra por error (``AllowAny`` o sin permisos) deja esto en rojo hasta
que alguien la anote aquí —un cambio de gate, aprobado en el chat— o la
cierre. Criterios BOT-01…04 y SEC-02 de la línea base de seguridad.
"""

import pytest
from django.conf import settings as dj_settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIClient

from tests.platform.routes import api_routes, is_format_twin, sample_url

#: Las únicas rutas que responden sin sesión, por su nombre en el URLconf.
PUBLIC_ROUTES: dict[str, str] = {
    "health": "liveness y versión de la API; no lee datos",
    "csrf": "deja la cookie CSRF que la SPA manda en cada escritura; no lee datos",
    "register": "registro con correo y contraseña (reCAPTCHA y campo trampa)",
    "verify-otp": "confirma la cuenta con el código que llegó por correo",
    "resend-otp": "vuelve a mandar el código de confirmación",
    "login": "abre la sesión web (cookies HttpOnly)",
    "password-reset": "pide el código para recuperar la contraseña",
    "password-reset-confirm": "cambia la contraseña con ese código",
    "refresh": "rota el refresh de la cookie; sin cookie válida, 401",
    "logout": "anula el refresh de la cookie que recibe y borra las cookies",
    "contact": "formulario de contacto del sitio (reCAPTCHA y campo trampa)",
    "documents": "términos y privacidad vigentes, para aceptarlos al registrarse",
    "document": "un documento legal vigente, para leerlo antes de entrar",
    "invitation-detail": "la invitación de su enlace: a quién invita y de dónde",
    "invitation-accept": "acepta la invitación: crea la cuenta o pide la contraseña",
}

#: Públicas sin un límite propio: quedan con el de ``anon``.
PUBLIC_WITHOUT_SCOPE: dict[str, str] = {
    "health": "una sonda; no lee datos",
    "csrf": "no lee datos ni cambia nada",
    "refresh": "solo sirve con un refresh vigente en la cookie",
    "logout": "solo anula el refresh que recibe",
    "documents": "texto público de solo lectura",
    "document": "texto público de solo lectura",
}

ROUTES = [route for route in api_routes() if not is_format_twin(route)]


def _is_public(route) -> bool:
    return not route.permissions or AllowAny in route.permissions


def test_every_throttle_scope_has_a_rate():
    """Un ``throttle_scope`` sin tasa hace que ScopedRateThrottle responda 500."""
    rates = dj_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    missing = [
        f"{route.name}: {route.scope}"
        for route in ROUTES
        if route.scope and route.scope not in rates
    ]
    assert not missing, "agrega su tasa a DEFAULT_THROTTLE_RATES:\n" + "\n".join(
        missing
    )


def test_only_the_known_routes_answer_without_a_session():
    """BOT-01: una ruta nueva abierta por error no pasa el gate."""
    public = {route.name for route in ROUTES if _is_public(route)}

    opened = sorted(public - set(PUBLIC_ROUTES))
    assert not opened, (
        "estas rutas responden sin sesión: ciérralas (IsAuthenticated) o anótalas "
        "en PUBLIC_ROUTES con su motivo:\n" + "\n".join(opened)
    )
    stale = sorted(set(PUBLIC_ROUTES) - public)
    assert not stale, "ya no son públicas; quítalas de PUBLIC_ROUTES:\n" + (
        "\n".join(stale)
    )


def test_public_routes_declare_a_scope():
    """BOT-03: cada puerta pública tiene su propio límite, o dice por qué no."""
    offenders = sorted(
        route.name
        for route in ROUTES
        if _is_public(route)
        and not route.scope
        and route.name not in PUBLIC_WITHOUT_SCOPE
    )
    assert not offenders, (
        "declara su throttle_scope (o el motivo en PUBLIC_WITHOUT_SCOPE):\n"
        + "\n".join(offenders)
    )


def test_private_routes_require_an_authenticated_user():
    """SEC-02: fuera de la lista blanca, toda vista exige la sesión."""
    offenders = sorted(
        f"{route.name} ({route.route})"
        for route in ROUTES
        if not _is_public(route)
        and not any(issubclass(p, IsAuthenticated) for p in route.permissions)
    )
    assert not offenders, "agrega IsAuthenticated a sus permisos:\n" + "\n".join(
        offenders
    )


@pytest.mark.django_db
def test_private_routes_answer_401_without_a_session():
    """SEC-02: sin sesión, cada método de cada ruta privada responde 401.

    401 y no 403: la SPA renueva la sesión con un 401 y muestra «sin permiso» con
    un 403. La autenticación por cookie declara ``authenticate_header``.
    """
    client = APIClient()
    offenders, checked = [], 0
    for route in ROUTES:
        if _is_public(route):
            continue
        url = sample_url(route)
        for method in route.methods:
            checked += 1
            response = client.generic(method.upper(), url)
            if response.status_code != status.HTTP_401_UNAUTHORIZED:
                offenders.append(
                    f"{method.upper()} {url} ({route.name}): {response.status_code}"
                )
    assert checked > 50, f"solo {checked} peticiones: ¿cambió el URLconf?"
    assert not offenders, "responden sin sesión o con otro estado:\n" + "\n".join(
        offenders
    )
