"""Respuestas de error de la API en palabras de la aplicación."""

import math

from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler as drf_exception_handler


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
    """El de DRF, con el 429 dicho como lo diría la aplicación."""
    if isinstance(exc, Throttled):
        exc.detail = f"Demasiados intentos. {_wait_text(exc.wait)}"
    return drf_exception_handler(exc, context)
