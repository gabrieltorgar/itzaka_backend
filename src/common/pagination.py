"""Paginación de todas las listas (iteracion-17 #1, api-lists-errors.md §1)."""

from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """?page=&page_size= → {"count", "next", "previous", "results"}.

    El servidor corta siempre la página: sin pedirla llegan las 20 primeras, y
    nunca más de 100. La pantalla pide solo lo que muestra en lugar de bajar la
    cuenta entera para paginarla en el navegador (US-77).
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        # Un ?ordering= del cliente reemplaza el orden de la vista y su
        # desempate: sin la pk, las filas empatadas se repetirían o se
        # perderían entre una página y la siguiente.
        if isinstance(queryset, QuerySet):
            ordering = tuple(queryset.query.order_by) or tuple(
                queryset.model._meta.ordering
            )
            if not {"id", "-id", "pk", "-pk"} & {
                o for o in ordering if isinstance(o, str)
            }:
                queryset = queryset.order_by(*ordering, "pk")
        return super().paginate_queryset(queryset, request, view)
