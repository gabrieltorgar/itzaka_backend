"""Cada documento nace con su folio (iteracion-25 #2 · US-142).

Cotización, estado del proyecto, comprobante de pago y comprobante de pago a
personal: el folio lo pone el servidor al crearlo, viaja en la API, no se
cambia por edición y se busca. Los documentos que ya existían conservan el
que imprimían (``COT-`` y los primeros ocho caracteres de su id).
"""

import importlib
import re
import uuid

import pytest
from django.apps import apps as django_apps
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.folios.codes import DocumentType, Mode, legacy_folio
from apps.folios.models import IssuedFolio
from apps.folios.services import configure_folios
from apps.payments.models import Payment
from apps.projects.models import Project
from apps.quotes.models import Quote
from apps.staff.models import WorkerPayment
from apps.staff.tests.factories import WorkerFactory

AUTO = r"^{}-[0-9A-F]{{8}}$"


def quote_payload(user) -> dict:
    client = ClientFactory(owner=user)
    tariff = TariffFactory(owner=user, unit_price="350")
    return {
        "client": str(client.id),
        "items": [{"tariff": str(tariff.id), "quantity": "2"}],
    }


def post_quote(api, user) -> dict:
    response = api.post("/api/quotes/", quote_payload(user), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    return response.data


@pytest.mark.django_db
class TestCadaDocumentoNaceConSuFolio:
    def test_a_quote_gets_its_folio_from_the_server(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - La cotización trae su folio en la respuesta."""
        created = post_quote(authenticated_client, user)

        assert re.match(AUTO.format("COT"), created["folio"])
        detail = authenticated_client.get(f"/api/quotes/{created['id']}/")
        assert detail.data["folio"] == created["folio"]

    def test_a_sequential_quote_uses_the_prefix(
        self, authenticated_client, user
    ) -> None:
        configure_folios(
            owner=user,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="OBR",
        )

        folios = [post_quote(authenticated_client, user)["folio"] for _ in range(2)]

        assert folios == ["OBR-1", "OBR-2"]

    def test_changing_the_mode_does_not_touch_existing_documents(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Los documentos ya creados conservan su folio."""
        first = post_quote(authenticated_client, user)
        configure_folios(
            owner=user,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="OBR",
        )
        post_quote(authenticated_client, user)

        again = authenticated_client.get(f"/api/quotes/{first['id']}/")

        assert again.data["folio"] == first["folio"]

    def test_the_folio_cannot_be_changed_by_editing(
        self, authenticated_client, user
    ) -> None:
        """Criterio - SEC-03 · Mandar otro folio al editar no lo cambia."""
        created = post_quote(authenticated_client, user)
        payload = {**quote_payload(user), "folio": "COT-1"}

        response = authenticated_client.put(
            f"/api/quotes/{created['id']}/", payload, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["folio"] == created["folio"]

    def test_quotes_are_found_by_folio(self, authenticated_client, user) -> None:
        configure_folios(
            owner=user,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="OBR",
        )
        post_quote(authenticated_client, user)
        wanted = post_quote(authenticated_client, user)

        response = authenticated_client.get("/api/quotes/", {"search": "OBR-2"})

        assert [row["id"] for row in response.data["results"]] == [str(wanted["id"])]

    def test_project_payment_and_worker_payment_get_their_folio(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Estado del proyecto y comprobantes de pago."""
        quote = post_quote(authenticated_client, user)
        project = authenticated_client.post("/api/projects/", {"quote": quote["id"]})
        payment = authenticated_client.post(
            "/api/payments/",
            {"project": project.data["id"], "amount": "100", "date": "2026-10-30"},
        )
        worker = WorkerFactory(owner=user)
        paid = authenticated_client.post(
            "/api/worker-payments/",
            {"worker": str(worker.id), "amount": "100", "date": "2026-10-30"},
        )

        assert re.match(AUTO.format("PRO"), project.data["folio"])
        assert re.match(AUTO.format("REC"), payment.data["folio"])
        assert re.match(AUTO.format("PAG"), paid.data["folio"])
        listed = authenticated_client.get("/api/projects/")
        assert listed.data["results"][0]["folio"] == project.data["folio"]

    def test_every_folio_is_registered_once_for_the_company(
        self, authenticated_client, user
    ) -> None:
        created = post_quote(authenticated_client, user)

        assert (
            IssuedFolio.objects.filter(owner=user, folio=created["folio"]).count() == 1
        )


@pytest.mark.django_db
class TestLosDocumentosQueYaExistian:
    def test_legacy_folio_is_what_the_pdf_printed(self) -> None:
        """El mismo cálculo que hacía el navegador: prefijo y ocho caracteres del id."""
        value = uuid.UUID("1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d")

        assert legacy_folio("COT", value) == "COT-1A2B3C4D"

    @pytest.mark.parametrize(
        ("module", "model", "prefix"),
        [
            ("apps.quotes.migrations.0007_quote_folio", Quote, "COT"),
            ("apps.projects.migrations.0005_project_folio", Project, "PRO"),
            ("apps.payments.migrations.0003_payment_folio", Payment, "REC"),
            ("apps.staff.migrations.0003_workerpayment_folio", WorkerPayment, "PAG"),
        ],
    )
    def test_existing_documents_keep_their_printed_folio(
        self, authenticated_client, user, module, model, prefix
    ) -> None:
        """Caso de borde - La migración guarda el folio que el PDF ya imprimía."""
        quote = post_quote(authenticated_client, user)
        project = authenticated_client.post("/api/projects/", {"quote": quote["id"]})
        authenticated_client.post(
            "/api/payments/",
            {"project": project.data["id"], "amount": "100", "date": "2026-10-30"},
        )
        authenticated_client.post(
            "/api/worker-payments/",
            {
                "worker": str(WorkerFactory(owner=user).id),
                "amount": "1",
                "date": "2026-10-30",
            },
        )
        IssuedFolio.objects.all().delete()
        row = model.objects.get(owner=user)
        model.objects.filter(pk=row.pk).update(folio="")

        importlib.import_module(module).backfill_folios(django_apps, None)

        row.refresh_from_db()
        assert row.folio == legacy_folio(prefix, row.pk)
        assert IssuedFolio.objects.filter(owner=user, folio=row.folio).exists()

    def test_two_old_documents_with_the_same_start_get_distinct_folios(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Dos ids que empiezan igual no repiten folio."""
        first = Quote.objects.get(pk=post_quote(authenticated_client, user)["id"])
        twin = uuid.UUID(str(first.pk)[:8] + "-0000-4000-8000-000000000000")
        Quote.objects.create(id=twin, owner=user, client=first.client)
        IssuedFolio.objects.all().delete()
        for pk in Quote.objects.values_list("pk", flat=True):
            Quote.objects.filter(pk=pk).update(folio=str(pk))

        importlib.import_module(
            "apps.quotes.migrations.0007_quote_folio"
        ).backfill_folios(django_apps, None)

        folios = list(
            Quote.objects.order_by("created_at").values_list("folio", flat=True)
        )
        assert len(set(folios)) == 2
        assert folios[0] == legacy_folio("COT", first.pk)
