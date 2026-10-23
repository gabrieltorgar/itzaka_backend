"""Acciones en lote sobre la selección de una lista (api-lists-errors.md §4).

Cada recurso declara ``POST /api/<recurso>/bulk/<acción>/``. El cuerpo trae los
ids elegidos o «todos los resultados» (``select_all``) con la misma búsqueda y
filtros de la lista en la query string; el servidor vuelve a resolver el
conjunto dentro de lo que la cuenta puede ver y nunca confía en un conteo del
cliente.
"""

from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import QuerySet
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

NOT_FOUND = "No encontrado."


def bulk_max_items() -> int:
    """Tope de registros por acción: settings.BULK_MAX_ITEMS (500)."""
    return getattr(settings, "BULK_MAX_ITEMS", 500)


class BulkSelectionSerializer(serializers.Serializer):
    """{"ids": [...]} o {"select_all": true, "exclude_ids": [...]}, uno solo."""

    ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False
    )
    select_all = serializers.BooleanField(default=False)
    exclude_ids = serializers.ListField(child=serializers.UUIDField(), default=list)

    def _capped(self, value: list) -> list:
        limit = self.context.get("max_items") or bulk_max_items()
        if len(value) > limit:
            raise serializers.ValidationError(
                f"Puedes seleccionar hasta {limit} registros por acción."
            )
        return list(dict.fromkeys(value))

    def validate_ids(self, value: list) -> list:
        return self._capped(value)

    def validate_exclude_ids(self, value: list) -> list:
        return self._capped(value)

    def validate(self, attrs: dict) -> dict:
        if attrs["select_all"] and attrs.get("ids"):
            raise serializers.ValidationError("Envía ids o select_all, no ambos.")
        if not attrs["select_all"] and not attrs.get("ids"):
            raise serializers.ValidationError("Selecciona al menos un registro.")
        if attrs["exclude_ids"] and not attrs["select_all"]:
            raise serializers.ValidationError(
                {"exclude_ids": "Solo aplica con select_all."}
            )
        return attrs


def error_text(exc: Exception) -> str:
    """El motivo que va en ``failed``: el texto del error, sea de DRF o de Django."""
    messages = getattr(exc, "messages", None)
    if messages is not None:
        return " ".join(str(message) for message in messages)
    detail = getattr(exc, "detail", exc)
    if isinstance(detail, dict):
        parts = [
            item
            for value in detail.values()
            for item in (value if isinstance(value, list) else [value])
        ]
        return " ".join(str(part) for part in parts)
    if isinstance(detail, list):
        return " ".join(str(part) for part in detail)
    return str(detail)


@dataclass
class BulkResult:
    """Lo que hizo una acción en lote; es el cuerpo de su respuesta 200."""

    requested: int = 0
    processed: int = 0
    failed: list[dict[str, str]] = field(default_factory=list)

    def fail(self, item_id: object, detail: object) -> None:
        self.failed.append({"id": str(item_id), "detail": str(detail)})

    def as_dict(self) -> dict:
        return {
            "requested": self.requested,
            "processed": self.processed,
            "failed": self.failed,
        }


class BulkActionMixin:
    """Resuelve la selección sobre la lista acotada (y filtrada) de la vista."""

    throttle_scope: str | None = None

    def get_bulk_queryset(
        self, request: Request, *, max_items: int | None = None
    ) -> QuerySet:
        """``max_items``: un tope menor para las costosas (BULK_COSTLY_MAX_ITEMS)."""
        limit = max_items or bulk_max_items()
        selection = BulkSelectionSerializer(
            data=request.data, context={"max_items": limit}
        )
        selection.is_valid(raise_exception=True)
        data = selection.validated_data
        if data["select_all"]:
            # La misma query string que la lista: alcance + filtros + búsqueda.
            queryset = self.filter_queryset(self.get_queryset()).exclude(
                pk__in=data["exclude_ids"]
            )
            total = queryset.count()
            if total > limit:
                raise serializers.ValidationError(
                    {
                        "select_all": [
                            f"La selección tiene {total} registros; el máximo por "
                            f"acción es {limit}. Acota los filtros."
                        ]
                    }
                )
            self._bulk_missing: list[str] = []
            return queryset
        queryset = self.get_queryset().filter(pk__in=data["ids"])
        found = {str(pk) for pk in queryset.values_list("pk", flat=True)}
        # Lo ajeno o inexistente se informa como no encontrado y no se toca;
        # la respuesta no revela si existe en otra cuenta.
        self._bulk_missing = [
            str(item) for item in data["ids"] if str(item) not in found
        ]
        return queryset

    def bulk_response(self, result: BulkResult) -> Response:
        """200 con el BulkResult, sumando los ids que no se encontraron."""
        missing = getattr(self, "_bulk_missing", [])
        for item_id in missing:
            result.fail(item_id, NOT_FOUND)
        result.requested += len(missing)
        return Response(result.as_dict())
