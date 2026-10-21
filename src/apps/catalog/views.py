"""Catalog views: account-scoped tariff CRUD."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.catalog.selectors import list_tariffs_for_owner
from apps.catalog.serializers import TariffSerializer
from apps.catalog.services import delete_tariff
from apps.team.tenancy import account_of


class TariffViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated account's tariffs (isolated per account)."""

    serializer_class = TariffSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_tariffs_for_owner(owner=account_of(self.request))

    def perform_create(self, serializer) -> None:
        serializer.save(owner=account_of(self.request))

    def perform_destroy(self, instance) -> None:
        delete_tariff(tariff=instance)
