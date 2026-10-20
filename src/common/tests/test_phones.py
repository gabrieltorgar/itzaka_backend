"""Teléfonos validados y en un solo formato (iteracion-13 #3, MAN-05).

US-07 · US-08 · US-118 · US-96 · US-83. Un teléfono se escribe como sea —con
espacios, guiones o paréntesis— y se guarda en E.164 (+525512345678). Se lee
como lo escribiría una persona en México: los de México sin la lada del país
(55 1234 5678) y los de fuera con la suya. Uno que no es teléfono se rechaza.
"""

import pytest
from rest_framework import status

from apps.accounts.services import get_my_organization
from apps.clients.models import Client
from apps.leads.models import Lead
from apps.staff.models import Worker
from common.phones import normalize_existing

INVALIDO = "Escribe un teléfono válido, con su lada."


@pytest.mark.django_db
class TestTelefonoDelCliente:
    """US-07 / US-08."""

    def test_any_spelling_is_stored_once_and_read_nicely(
        self, authenticated_client
    ) -> None:
        response = authenticated_client.post(
            "/api/clients/", {"name": "Constructora Reyes", "phone": "(55) 1234-5678"}
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["phone"] == "55 1234 5678"
        assert str(Client.objects.get().phone) == "+525512345678"

    def test_a_foreign_number_keeps_its_country_code(
        self, authenticated_client
    ) -> None:
        response = authenticated_client.post(
            "/api/clients/", {"name": "Studio NY", "phone": "+1 212 555 0123"}
        )

        assert response.data["phone"] == "+1 212-555-0123"

    def test_something_that_is_not_a_phone_is_refused(
        self, authenticated_client
    ) -> None:
        response = authenticated_client.post(
            "/api/clients/", {"name": "Reyes", "phone": "555-1234"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["phone"] == [INVALIDO]
        assert not Client.objects.exists()

    def test_the_phone_stays_optional(self, authenticated_client) -> None:
        response = authenticated_client.post(
            "/api/clients/", {"name": "Sin teléfono", "phone": ""}
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["phone"] == ""


@pytest.mark.django_db
class TestTelefonoEnLosDemas:
    """US-118, US-96 y US-83 validan igual."""

    def test_organization(self, authenticated_client, user) -> None:
        bueno = authenticated_client.patch(
            "/api/auth/organization/", {"phone": "55 1234 5678"}, format="json"
        )
        malo = authenticated_client.patch(
            "/api/auth/organization/", {"phone": "12"}, format="json"
        )

        assert bueno.data["phone"] == "55 1234 5678"
        assert malo.status_code == status.HTTP_400_BAD_REQUEST
        assert str(get_my_organization(user=user).phone) == "+525512345678"

    def test_staff(self, authenticated_client) -> None:
        response = authenticated_client.post(
            "/api/workers/",
            {"name": "Luis", "kind": Worker.Kind.PERSON, "phone": "abc"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["phone"] == [INVALIDO]

    def test_contact(self, api_client) -> None:
        response = api_client.post(
            "/api/contact/", {"name": "Ana", "phone": "5512345678"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert str(Lead.objects.get().phone) == "+525512345678"


@pytest.mark.django_db
class TestLosQueYaEstaban:
    """La migración pasa a E.164 lo que se puede leer y no pierde lo demás."""

    def test_existing_phones_are_normalized_without_losing_any(self, user) -> None:
        legible = Client.objects.create(owner=user, name="A", phone="55-1234-5678")
        raro = Client.objects.create(owner=user, name="B", phone="ext. 12")

        normalize_existing(Client, "phone")

        legible.refresh_from_db()
        raro.refresh_from_db()
        assert str(legible.phone) == "+525512345678"
        assert raro.phone.raw_input == "ext. 12"
