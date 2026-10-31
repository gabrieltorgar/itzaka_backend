"""Línea base del dominio: los campos protegidos no se escriben por la API (TDD-B01).

No sale de una historia (iteracion-25 #10): dueño, empresa, rol, estado y montos
cambian solo por su acción, nunca porque el cliente los mande (SEC-03). La
inspección es estática: ningún serializer se instancia, así que sus querysets
acotados nunca corren.
"""

import inspect
import re
from importlib import import_module
from importlib.util import find_spec

from django.apps import apps
from rest_framework import serializers

PROTECTED = re.compile(
    r"^(?:(?:owner|company|created_by|approved_by|status_changed_by|role)(?:_id)?"
    r"|is_staff|is_superuser|permissions"
    r"|status|[a-z]+_status|status_changed_at|subtotal|tax|total|[a-z_]+_total"
    r"|discount|discount_amount|refunded_amount|refund_amount|credit_amount|balance"
    r"|paid_at|approved_at|converted_at)$"
)
#: Campos protegidos que un serializer declara sin read_only, con el porqué.
WRITABLE_PROTECTED: dict[str, str] = {
    "apps.quotes.serializers.QuoteSerializer.status": (
        "forma de lectura: crear y editar pasan por QuoteWriteSerializer, sin status"
    ),
    "apps.projects.serializers.ProjectSerializer.status": (
        "forma de lectura: el proyecto nace con StartProjectSerializer y su ruta "
        "no tiene PUT ni PATCH"
    ),
    "apps.projects.serializers.ProjectListSerializer.status": (
        "forma de lectura de la lista (GET)"
    ),
}


def _app_modules(name: str):
    for config in apps.get_app_configs():
        if config.name.startswith("apps.") and find_spec(f"{config.name}.{name}"):
            yield import_module(f"{config.name}.{name}")


def _model_serializers():
    for module in _app_modules("serializers"):
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, serializers.ModelSerializer)
                and obj.__module__ == module.__name__
            ):
                yield obj


def _read_only(cls, name: str) -> bool:
    meta, declared = cls.Meta, cls._declared_fields.get(name)
    return (
        name in getattr(meta, "read_only_fields", ())
        or getattr(meta, "extra_kwargs", {}).get(name, {}).get("read_only") is True
        or (
            declared is not None
            and (declared.read_only or isinstance(declared, serializers.HiddenField))
        )
    )


def test_protected_fields_are_read_only():
    """SEC-03: un campo protegido escribible lleva su motivo en WRITABLE_PROTECTED."""
    offenders, seen = [], set()
    for cls in _model_serializers():
        for name in getattr(cls.Meta, "fields", ()):
            key = f"{cls.__module__}.{cls.__qualname__}.{name}"
            if not PROTECTED.match(name) or _read_only(cls, name):
                continue
            seen.add(key)
            if key not in WRITABLE_PROTECTED:
                line = inspect.getsourcelines(cls)[1]
                offenders.append(f"{inspect.getsourcefile(cls)}:{line} {key}")
    assert not offenders, (
        "los campos protegidos cambian solo por su acción (security.md §3):\n"
        + "\n".join(offenders)
    )
    stale = sorted(set(WRITABLE_PROTECTED) - seen)
    assert not stale, "ya son de solo lectura; quítalos de WRITABLE_PROTECTED:\n" + (
        "\n".join(stale)
    )
