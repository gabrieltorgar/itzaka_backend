"""Buscar y ordenar el texto de las listas sin acentos ni mayúsculas (US-79).

«mucino» encuentra a «Muciño», y «Ébano» va antes que «flores», como lo hacía
el navegador cuando la lista vivía entera en memoria. La comparación se hace en
la base con una transformación propia: ``TRANSLATE`` en PostgreSQL (CI y Neon,
sin depender de la extensión ``unaccent``) y una función registrada en la
conexión en SQLite (pruebas locales). Las dos cambian las mismas letras.
"""

import unicodedata

from django.db.models import CharField, F, TextField, Transform
from django.db.models.functions import Lower
from rest_framework.filters import OrderingFilter, SearchFilter

# Las mayúsculas se arman al cargar el módulo: escritas en el código, algunas
# (como la A con acento) no se leen en cp1252 y las pruebas base que recorren
# el código en Windows fallarían.
_LOWER = "áàâäãéèêëíìîïóòôöõúùûüñç"
ACCENTED = _LOWER + _LOWER.upper()
PLAIN = "".join(unicodedata.normalize("NFD", letter)[0] for letter in ACCENTED)
_TABLE = str.maketrans(ACCENTED, PLAIN)
SQLITE_FUNCTION = "UNACCENTED"


def strip_accents(value: str | None) -> str | None:
    """Las letras acentuadas de ACCENTED por las simples; lo demás igual."""
    return None if value is None else str(value).translate(_TABLE)


def _register_sqlite_function(connection) -> None:
    # Registrar es barato e idempotente; la conexión pudo abrirse antes de que
    # este módulo se importara, así que se hace al compilar cada consulta.
    connection.ensure_connection()
    connection.connection.create_function(
        SQLITE_FUNCTION, 1, strip_accents, deterministic=True
    )


class Unaccented(Transform):
    """El texto con las letras acentuadas cambiadas por las simples.

    Bilateral: se aplica a la columna y también al término buscado, así que
    «pérez» y «perez» encuentran lo mismo.
    """

    lookup_name = "unaccented"
    bilateral = True

    def as_sql(self, compiler, connection):
        sql, params = compiler.compile(self.lhs)
        return f"TRANSLATE({sql}, %s, %s)", [*params, ACCENTED, PLAIN]

    def as_sqlite(self, compiler, connection):
        _register_sqlite_function(connection)
        sql, params = compiler.compile(self.lhs)
        return f"{SQLITE_FUNCTION}({sql})", params


CharField.register_lookup(Unaccented)
TextField.register_lookup(Unaccented)


class AccentInsensitiveSearchFilter(SearchFilter):
    """SearchFilter de DRF con ``icontains`` sin acentos en cada campo de texto."""

    def construct_search(self, field_name, queryset):
        lookup = super().construct_search(field_name, queryset)
        if lookup.endswith("__icontains"):
            return lookup.removesuffix("__icontains") + "__unaccented__icontains"
        return lookup


class AccentInsensitiveOrderingFilter(OrderingFilter):
    """OrderingFilter de DRF que ordena el texto como lo lee una persona.

    Los campos de ``view.ordering_text_fields`` se ordenan sin acentos ni
    mayúsculas: con la intercalación C de PostgreSQL, «Ébano» quedaría después
    de «zapata». Los demás (fechas, importes) se ordenan tal cual.
    """

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)
        if not ordering:
            return queryset
        text_fields = set(getattr(view, "ordering_text_fields", ()))
        terms = []
        for term in ordering:
            name = term.lstrip("-")
            if name in text_fields:
                key = Lower(Unaccented(F(name)))
                terms.append(key.desc() if term.startswith("-") else key.asc())
            else:
                terms.append(term)
        return queryset.order_by(*terms)
