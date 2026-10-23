"""Trabajar en las empresas que me invitan (iteracion-14 #3, US-137 · US-126).

Un colaborador trabaja sobre los datos de la empresa —los del administrador—,
no sobre los suyos. La aplicación dice en qué empresa trabaja con la cabecera
``X-Empresa``; sin ella, se usa la empresa propia o, a falta de una, la primera
donde colabora. Una empresa donde no colabora, o donde está desactivado, no
existe para él.
"""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import get_my_organization
from apps.accounts.tests.factories import UserFactory
from apps.clients.models import Client
from apps.clients.tests.factories import ClientFactory
from apps.quotes.models import Quote
from apps.team.models import Membership
from apps.team.tests.factories import MembershipFactory
from common.tests.test_cross_account import cuenta_completa


def empresa(nombre: str) -> User:
    admin = UserFactory()
    organizacion = get_my_organization(user=admin)
    organizacion.name = nombre
    organizacion.save()
    return admin


def como(user: User, empresa_id=None) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    if empresa_id is not None:
        client.credentials(HTTP_X_EMPRESA=str(empresa_id))
    return client


@pytest.fixture
def reyes(db):
    admin = empresa("Estudio Reyes")
    return admin, cuenta_completa(admin)


@pytest.fixture
def colaborador(reyes):
    """Ana: colabora en Estudio Reyes y no tiene empresa propia."""
    return MembershipFactory(account=reyes[0]).user


@pytest.mark.django_db
class TestLosDatosDeLaEmpresa:
    """Flujo principal - Los datos de la empresa."""

    @pytest.mark.parametrize(
        "url",
        [
            "/api/clients/",
            "/api/tariffs/",
            "/api/quotes/",
            "/api/projects/",
            "/api/workers/",
            "/api/plans/",
        ],
    )
    def test_the_collaborator_sees_the_company_lists(
        self, reyes, colaborador, url
    ) -> None:
        response = como(colaborador).get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_what_they_create_belongs_to_the_company(self, reyes, colaborador):
        admin, _ = reyes

        response = como(colaborador).post(
            "/api/clients/", {"name": "Familia Ortega"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Client.objects.get(name="Familia Ortega").owner == admin

    def test_company_records_can_be_referenced(self, reyes, colaborador) -> None:
        """Una cotización con el cliente y el servicio de la empresa."""
        admin, datos = reyes

        response = como(colaborador).post(
            "/api/quotes/",
            {
                "client": str(datos["client"].id),
                "items": [{"tariff": str(datos["tariff"].id), "quantity": "3"}],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Quote.objects.filter(owner=admin).count() == 2

    def test_the_project_and_its_payments(self, reyes, colaborador) -> None:
        _, datos = reyes
        proyecto = datos["project"]

        detalle = como(colaborador).get(f"/api/projects/{proyecto.id}/")
        pagos = como(colaborador).get("/api/payments/", {"project": proyecto.id})

        assert detalle.status_code == status.HTTP_200_OK
        assert pagos.status_code == status.HTTP_200_OK
        assert len(pagos.data["results"]) == 1

    def test_the_dashboard_is_the_company_one(self, reyes, colaborador) -> None:
        response = como(colaborador).get("/api/dashboard/")

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(str(response.data["quoted_value"])) > 0

    def test_documents_carry_the_company_brand(
        self, reyes, colaborador, settings, mocker
    ) -> None:
        settings.RESEND_API_KEY = "re_test"
        enviar = mocker.patch("common.mail.send_email", return_value=True)

        como(colaborador).post(
            "/api/documents/send/",
            {
                "kind": "quote",
                "to": "cliente@correo.mx",
                "file": SimpleUploadedFile("c.pdf", b"%PDF-1.4 x", "application/pdf"),
            },
            format="multipart",
        )

        llamada = enviar.call_args.kwargs
        assert "Estudio Reyes" in llamada["subject"]
        # Las respuestas le llegan a quien lo mandó.
        assert llamada["reply_to"] == colaborador.email

    def test_the_organization_is_the_company_one(self, reyes, colaborador) -> None:
        response = como(colaborador).get("/api/auth/organization/")

        assert response.data["name"] == "Estudio Reyes"


@pytest.mark.django_db
class TestCambiarDeEmpresa:
    """Flujo principal - Cambiar de empresa con la cabecera X-Empresa."""

    def test_the_header_chooses_among_their_companies(self, reyes, colaborador):
        otra = empresa("Despacho Lumen")
        ClientFactory(owner=otra, name="Hostal Mirador")
        MembershipFactory(account=otra, user=colaborador)

        en_reyes = como(colaborador, reyes[0].id).get("/api/clients/")
        en_lumen = como(colaborador, otra.id).get("/api/clients/")

        assert [c["name"] for c in en_reyes.data["results"]] == ["Constructora Reyes"]
        assert [c["name"] for c in en_lumen.data["results"]] == ["Hostal Mirador"]

    def test_an_administrator_works_in_their_own_by_default(self, reyes) -> None:
        admin, _ = reyes
        otra = empresa("Despacho Lumen")
        MembershipFactory(account=otra, user=admin)

        propia = como(admin).get("/api/clients/")
        ajena = como(admin, otra.id).get("/api/clients/")

        assert len(propia.data["results"]) == 1
        assert ajena.data["results"] == []


@pytest.mark.django_db
class TestAislamiento:
    """Caso de borde - Una empresa donde no colabora no existe para él."""

    def test_a_company_they_do_not_belong_to_is_refused(self, reyes, colaborador):
        ajena = empresa("Otra")

        response = como(colaborador, ajena.id).get("/api/clients/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == "company_access"

    def test_a_record_of_another_company_is_not_found(self, reyes, colaborador):
        ajeno = ClientFactory()

        response = como(colaborador).get(f"/api/clients/{ajeno.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_a_malformed_header_is_refused(self, reyes, colaborador) -> None:
        response = como(colaborador, "no-es-un-id").get("/api/clients/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_someone_else_cannot_borrow_your_company(self, reyes) -> None:
        """Una cuenta cualquiera no entra a otra empresa con sólo nombrarla."""
        admin, _ = reyes
        intruso = UserFactory()

        response = como(intruso, admin.id).get("/api/clients/")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestDesactivado:
    """Caso de borde - Sin empresas activas."""

    def test_a_deactivated_collaborator_is_left_out(self, reyes, colaborador):
        Membership.objects.filter(user=colaborador).update(is_active=False)

        con_cabecera = como(colaborador, reyes[0].id).get("/api/clients/")
        sin_cabecera = como(colaborador).get("/api/clients/")

        assert con_cabecera.status_code == status.HTTP_403_FORBIDDEN
        assert "desactivado" in con_cabecera.data["detail"]
        assert sin_cabecera.status_code == status.HTTP_403_FORBIDDEN
        assert "no tienes una empresa activa" in sin_cabecera.data["detail"].lower()

    def test_without_a_company_their_own_account_still_works(self, colaborador):
        """El perfil es de la persona: se puede ver aunque no tenga empresa."""
        Membership.objects.filter(user=colaborador).update(is_active=False)

        response = como(colaborador).get("/api/auth/me/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["companies"] == []


@pytest.mark.django_db
class TestMisEmpresas:
    """La cuenta dice en qué empresas trabaja y con qué papel."""

    def test_a_collaborator_lists_only_active_companies(self, reyes, colaborador):
        otra = empresa("Despacho Lumen")
        MembershipFactory(account=otra, user=colaborador, is_active=False)

        response = como(colaborador).get("/api/auth/me/")

        assert response.data["companies"] == [
            {"id": str(reyes[0].id), "name": "Estudio Reyes", "role": "collaborator"}
        ]

    def test_an_administrator_has_their_own_first(self, reyes) -> None:
        admin, _ = reyes
        otra = empresa("Despacho Lumen")
        MembershipFactory(account=otra, user=admin)

        response = como(admin).get("/api/auth/me/")

        assert response.data["companies"] == [
            {"id": str(admin.id), "name": "Estudio Reyes", "role": "admin"},
            {"id": str(otra.id), "name": "Despacho Lumen", "role": "collaborator"},
        ]


@pytest.mark.django_db
class TestColaboradorQueSeVa:
    """US-126: un colaborador que elimina su cuenta no borra nada de la empresa."""

    def test_deleting_their_account_keeps_the_company_data(self, reyes, colaborador):
        admin, _ = reyes
        colaborador.set_password("Teja-Roja-81")
        colaborador.save()
        como(colaborador).post(
            "/api/clients/", {"name": "Lo registró Ana"}, format="json"
        )

        response = como(colaborador).post(
            "/api/auth/me/delete/", {"password": "Teja-Roja-81"}, format="json"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not User.objects.filter(pk=colaborador.pk).exists()
        assert Client.objects.filter(owner=admin).count() == 2
        assert not Membership.objects.filter(account=admin).exists()


class TestCabeceraPermitida:
    """La cabecera X-Empresa pasa CORS si algún día se llama desde otro origen."""

    def test_cors_lets_the_company_header_through(self, settings) -> None:
        assert "x-empresa" in settings.CORS_ALLOW_HEADERS
