"""Respuestas de error de la API en palabras de la aplicación."""

import logging
import math

from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger("apps")

#: Lo que se le dice a la petición que perdió contra otra simultánea.
CONFLICT_MESSAGE = (
    "Otra petición hizo este mismo cambio al mismo tiempo. Actualiza y vuelve "
    "a intentarlo."
)


def _wait_text(seconds: float | None) -> str:
    if not seconds:
        return "Intenta de nuevo en un momento."
    seconds = math.ceil(seconds)
    if seconds < 60:
        unit = "segundo" if seconds == 1 else "segundos"
        return f"Intenta de nuevo en {seconds} {unit}."
    minutes = math.ceil(seconds / 60)
    unit = "minuto" if minutes == 1 else "minutos"
    return f"Intenta de nuevo en {minutes} {unit}."


def exception_handler(exc, context):
    """El de DRF, con el 429 dicho como lo diría la aplicación.

    Y dos peticiones que chocan con una restricción única de la base ya no
    terminan en un 500 (iteracion-16): la que perdió recibe 409 con qué hacer.
    El mensaje de la base —tablas, restricciones— nunca llega al cliente.
    """
    if isinstance(exc, IntegrityError):
        logger.warning("Integrity conflict: %s", type(exc).__name__)
        set_rollback()
        return Response(
            {"detail": CONFLICT_MESSAGE, "code": "conflict"},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, Throttled):
        exc.detail = f"Demasiados intentos. {_wait_text(exc.wait)}"
    return drf_exception_handler(exc, context)
