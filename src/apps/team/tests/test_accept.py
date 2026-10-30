"""Aceptar una invitación y crear la cuenta (iteracion-14 #2, US-136).

El enlace del correo abre /invitacion/<token>. La pantalla pregunta a la API de
quién es la invitación y en qué estado está; al aceptar, quien no tiene cuenta
la crea ya confirmada —el enlace llegó a su correo— y sin empresa propia, y
quien ya tiene cuenta escribe su contraseña. En los dos casos entra a la
empresa que lo invitó.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import Organization, Subscription, User
from apps.accounts.services import get_my_organization
from apps.accounts.tests.factories import UserFactory
from apps.legal.models import LegalAcceptance
from apps.legal.tests.consent import accepted
from apps.team.models import Invitation, Membership
from apps.team.tests.factories import InvitationFactory, MembershipFactory
from common import recaptcha

PASSWORD = "Teja-Roja-81"


def detalle(token: str) -> str:
    return f"/api/invitations/{token}/"


def aceptar(token: str) -> str:
    return f"/api/invitations/{token}/accept/"


@pytest.fixture
def invitacion(db):
    """Una invitación vigente de «Estudio Reyes» para ana@estudio.mx."""
    admin = UserFactory(email="admin@estudioreyes.mx")
    organizacion = get_my_organization(user=admin)
    organizacion.name = "Estudio Reyes"
    organizacion.save()
    return InvitationFactory(account=admin, email="ana@estudio.mx", token="enlace-ana")


@pytest.mark.django_db
class TestDeQuienEsLaInvitacion:
    """La pantalla sabe a qué empresa invita, a qué correo y si sigue sirviendo."""

    def test_a_pending_invitation_tells_the_company_and_email(
        self, api_client, invitacion
    ) -> None:
        response = api_client.get(detalle("enlace-ana"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["company"] == "Estudio Reyes"
        assert response.data["email"] == "ana@estudio.mx"
        assert response.data["status"] == "pending"
        assert response.data["account_exists"] is False

    def test_it_says_when_the_email_already_has_an_account(
        self, api_client, invitacion
    ) -> None:
        UserFactory(email="ana@estudio.mx")

        assert api_client.get(detalle("enlace-ana")).data["account_exists"] is True

    @pytest.mark.parametrize(
        ("cambios", "estado"),
        [
            ({"expires_at": timezone.now() - timedelta(minutes=1)}, "expired"),
            ({"status": Invitation.Status.CANCELLED}, "cancelled"),
            ({"status": Invitation.Status.ACCEPTED}, "accepted"),
        ],
    )
    def test_it_says_when_it_no_longer_works(
        self, api_client, invitacion, cambios, estado
    ) -> None:
        Invitation.objects.filter(pk=invitacion.pk).update(**cambios)

        assert api_client.get(detalle("enlace-ana")).data["status"] == estado

    def test_an_unknown_link_is_not_found(self, api_client, db) -> None:
        response = api_client.get(detalle("no-existe"))

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestCrearLaCuenta:
    """Flujo principal - Crear la cuenta."""

    def test_the_account_is_born_confirmed_and_inside_the_company(
        self, api_client, invitacion
    ) -> None:
        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        cuenta = User.objects.get(email="ana@estudio.mx")
        assert cuenta.is_email_verified is True
        assert cuenta.has_own_workspace is False
        assert cuenta.check_password(PASSWORD)
        assert Membership.objects.get(user=cuenta).account == invitacion.account
        invitacion.refresh_from_db()
        assert invitacion.status == Invitation.Status.ACCEPTED
        assert invitacion.accepted_at is not None

    def test_it_opens_the_session(self, api_client, invitacion) -> None:
        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert "itzaka_access" in response.cookies
        assert response.data["user"]["email"] == "ana@estudio.mx"

    def test_it_says_which_company_to_enter(self, api_client, invitacion) -> None:
        """Entra a ella: la aplicación sabe a qué empresa acaba de sumarse."""
        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert response.data["company"] == {
            "id": str(invitacion.account.id),
            "name": "Estudio Reyes",
        }

    def test_no_company_of_its_own_is_created(self, api_client, invitacion) -> None:
        api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        cuenta = User.objects.get(email="ana@estudio.mx")
        assert not Organization.objects.filter(user=cuenta).exists()
        assert not Subscription.objects.filter(user=cuenta).exists()

    def test_the_legal_documents_are_accepted(self, api_client, invitacion) -> None:
        api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert LegalAcceptance.objects.filter(user__email="ana@estudio.mx").count() == 2

    def test_without_accepting_the_terms_there_is_no_account(
        self, api_client, invitacion
    ) -> None:
        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "terms_version" in response.data
        assert not User.objects.filter(email="ana@estudio.mx").exists()

    def test_a_weak_password_is_refused(self, api_client, invitacion) -> None:
        response = api_client.post(
            aceptar("enlace-ana"), {"password": "12345678", **accepted()}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data
        invitacion.refresh_from_db()
        assert invitacion.status == Invitation.Status.PENDING


@pytest.mark.django_db
class TestYaTengoCuenta:
    """Caso alternativo - Ya tengo cuenta: la empresa se suma a las suyas."""

    def test_with_the_password_the_company_is_added(
        self, api_client, invitacion
    ) -> None:
        cuenta = UserFactory(email="ana@estudio.mx", password=PASSWORD)
        MembershipFactory(user=cuenta)  # ya colabora en otra empresa

        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email="ana@estudio.mx").count() == 1
        assert Membership.objects.filter(user=cuenta).count() == 2
        assert Membership.objects.filter(
            user=cuenta, account=invitacion.account
        ).exists()
        assert "itzaka_access" in response.cookies

    def test_a_wrong_password_adds_nothing(self, api_client, invitacion) -> None:
        cuenta = UserFactory(email="ana@estudio.mx", password=PASSWORD)

        response = api_client.post(
            aceptar("enlace-ana"), {"password": "otra-cosa-99"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["password"] == ["La contraseña no es correcta."]
        assert not Membership.objects.filter(user=cuenta).exists()
        assert "itzaka_access" not in response.cookies

    def test_an_unconfirmed_account_is_confirmed_by_the_link(
        self, api_client, invitacion
    ) -> None:
        """El enlace llegó a ese correo: eso ya lo confirma."""
        cuenta = UserFactory(
            email="ana@estudio.mx", password=PASSWORD, is_email_verified=False
        )

        api_client.post(aceptar("enlace-ana"), {"password": PASSWORD}, format="json")

        cuenta.refresh_from_db()
        assert cuenta.is_email_verified is True

    def test_an_administrator_keeps_their_own_company(
        self, api_client, invitacion
    ) -> None:
        cuenta = UserFactory(email="ana@estudio.mx", password=PASSWORD)

        api_client.post(aceptar("enlace-ana"), {"password": PASSWORD}, format="json")

        cuenta.refresh_from_db()
        assert cuenta.has_own_workspace is True


@pytest.mark.django_db
class TestEnlaceQueYaNoSirve:
    """Casos de borde - Vencida, cancelada o ya aceptada."""

    def test_an_expired_invitation_is_gone(self, api_client, invitacion) -> None:
        invitacion.expires_at = timezone.now() - timedelta(minutes=1)
        invitacion.save()

        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert response.status_code == status.HTTP_410_GONE
        assert "venció" in response.data["detail"]
        assert not User.objects.filter(email="ana@estudio.mx").exists()

    def test_a_cancelled_invitation_is_gone(self, api_client, invitacion) -> None:
        invitacion.status = Invitation.Status.CANCELLED
        invitacion.save()

        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert response.status_code == status.HTTP_410_GONE
        assert "canceló" in response.data["detail"]

    def test_the_link_works_only_once(self, api_client, invitacion) -> None:
        cuerpo = {"password": PASSWORD, **accepted()}
        api_client.post(aceptar("enlace-ana"), cuerpo, format="json")

        response = api_client.post(aceptar("enlace-ana"), cuerpo, format="json")

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "inicia sesión" in response.data["detail"]

    def test_an_unknown_link_creates_nothing(self, api_client, db) -> None:
        response = api_client.post(
            aceptar("no-existe"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not User.objects.exists()


@pytest.mark.django_db
class TestFormularioPublico:
    """Es un formulario que crea cuentas: reCAPTCHA y campo trampa, como el registro."""

    def test_a_bot_gets_the_usual_answer_and_no_account(
        self, api_client, invitacion
    ) -> None:
        response = api_client.post(
            aceptar("enlace-ana"),
            {"password": PASSWORD, "website": "http://spam", **accepted()},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert not User.objects.filter(email="ana@estudio.mx").exists()
        assert "itzaka_access" not in response.cookies

    def test_a_filled_trap_answers_with_the_shape_of_a_success(
        self, api_client, invitacion
    ) -> None:
        """Bug iteracion-16 - El campo trampa lleno no deja una sesión falsa.

        La respuesta se ve como la de siempre —con la empresa a la que se
        entra—, así que quien la lee no se rompe; la sesión no existe.
        """
        response = api_client.post(
            aceptar("enlace-ana"),
            {"password": PASSWORD, "website": "Estudio Reyes", **accepted()},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert set(response.data) == {"user", "company"}
        assert response.data["company"]["id"]
        assert response.data["company"]["name"] == "Estudio Reyes"
        assert response.data["user"]["email"] == "ana@estudio.mx"
        assert "itzaka_access" not in response.cookies
        invitacion.refresh_from_db()
        assert invitacion.status == Invitation.Status.PENDING
        assert not Membership.objects.exists()

    def test_a_low_score_is_refused(self, api_client, invitacion, settings, mocker):
        settings.RECAPTCHA_ENABLED = True
        settings.RECAPTCHA_SECRET_KEY = "secreta"
        settings.RECAPTCHA_MIN_SCORE = 0.5
        settings.RECAPTCHA_HOSTNAMES = ["cuotreka.vercel.app"]
        mocker.patch.object(
            recaptcha,
            "_siteverify",
            return_value={
                "success": True,
                "action": "invitation_accept",
                "hostname": "cuotreka.vercel.app",
                "score": 0.1,
            },
        )

        response = api_client.post(
            aceptar("enlace-ana"),
            {"password": PASSWORD, "recaptcha_token": "t", **accepted()},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not User.objects.filter(email="ana@estudio.mx").exists()


@pytest.mark.django_db
class TestDosAlMismoTiempo:
    """Bug iteracion-16 - Dos aceptaciones al mismo tiempo, sin error del sistema."""

    def test_an_account_created_meanwhile_asks_for_its_password(
        self, api_client, invitacion, mocker
    ) -> None:
        # La invitación de otra empresa al mismo correo acaba de crear la cuenta.
        UserFactory(email="ana@estudio.mx")
        mocker.patch("apps.team.services.find_user", return_value=None)

        response = api_client.post(
            aceptar("enlace-ana"), {"password": PASSWORD, **accepted()}, format="json"
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Ya existe una cuenta con este correo" in str(response.data["detail"])
        invitacion.refresh_from_db()
        assert invitacion.status == Invitation.Status.PENDING
        assert not Membership.objects.exists()
