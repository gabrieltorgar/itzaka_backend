"""Paginación opcional y con tope (iteracion-12 #6)."""

from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    """Pagina sólo cuando se pide; nunca más de 100 por página.

    Las pantallas de hoy leen cada lista entera —una cuenta tiene decenas de
    clientes, no miles—, así que sin ``page`` ni ``page_size`` la respuesta
    conserva su forma de lista. Quien pide una página recibe ``count``,
    ``next``, ``previous`` y ``results``, con ``page_size`` acotado a 100.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        params = request.query_params
        if (
            self.page_query_param not in params
            and self.page_size_query_param not in params
        ):
            return None
        return super().paginate_queryset(queryset, request, view)
