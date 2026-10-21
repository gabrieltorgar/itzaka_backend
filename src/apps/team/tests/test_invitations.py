"""Invitar colaboradores por correo (iteracion-14 #1, US-135).

El administrador —quien creó la cuenta— escribe uno o varios correos; a cada
uno le llega un enlace que vence en 7 días. El enlace es un secreto: en la base
sólo queda su huella, y quien lo tiene es quien recibió el correo.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from apps.accounts.services import get_my_organization
from apps.team.models import Invitation
from apps.team.services import hash_token
from apps.team.tests.factories import InvitationFactory, MembershipFactory

URL = "/api/collaborators/invitations/"


@pytest.fixture
def correo(settings, mocker):
    """El correo configurado, con el envío interceptado."""
    settings.RESEND_API_KEY = "re_test"
    settings.APP_BASE_URL = "https://cuotreka.vercel.app"
    return mocker.patch("apps.team.emails.mail.send_email", return_value=True)


def enlaces(correo):
    """El token de cada correo enviado, sacado del enlace del botón."""
    tokens = []
    for llamada in correo.call_args_list:
        html = llamada.kwargs["html"]
        inicio = html.index("/invitacion/") + len("/invitacion/")
        tokens.append(html[inicio : html.index('"', inicio)])
    return tokens


@pytest.mark.django_db
class TestInvitarAVarios:
    """Flujo principal - Invitar a varios."""

    def test_each_email_gets_its_own_link(self, authenticated_client, user, correo):
        response = authenticated_client.post(
            URL,
            {"emails": ["Ana@Estudio.mx", "luis@obra.mx"]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert [i["email"] for i in response.data["invited"]] == [
            "ana@estudio.mx",
            "luis@obra.mx",
        ]
        assert response.data["skipped"] == []
        assert correo.call_count == 2
        assert {c.kwargs["to"] for c in correo.call_args_list} == {
            "ana@estudio.mx",
            "luis@obra.mx",
        }
        invitaciones = Invitation.objects.filter(account=user)
        assert invitaciones.count() == 2
        assert set(invitaciones.values_list("status", flat=True)) == {"pending"}

    def test_the_link_is_valid_for_seven_days(
        self, authenticated_client, user, correo
    ) -> None:
        authenticated_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        invitacion = Invitation.objects.get()
        vigencia = invitacion.expires_at - timezone.now()
        assert timedelta(days=6, hours=23) < vigencia <= timedelta(days=7)
        assert "vence en 7 días" in correo.call_args.kwargs["html"]

    def test_only_a_fingerprint_of_the_link_is_kept(
        self, authenticated_client, correo
    ) -> None:
        authenticated_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        [token] = enlaces(correo)
        invitacion = Invitation.objects.get()
        assert len(token) >= 40
        assert invitacion.token_hash == hash_token(token)
        assert token not in invitacion.token_hash

    def test_the_email_speaks_for_the_company(
        self, authenticated_client, user, correo
    ) -> None:
        organizacion = get_my_organization(user=user)
        organizacion.name = "Estudio Reyes"
        organizacion.save()

        authenticated_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        llamada = correo.call_args.kwargs
        assert "Estudio Reyes" in llamada["subject"]
        assert "Estudio Reyes" in llamada["html"]
        assert "https://cuotreka.vercel.app/invitacion/" in llamada["html"]

    def test_the_same_email_twice_in_one_go_is_one_invitation(
        self, authenticated_client, correo
    ) -> None:
        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx", " ANA@estudio.mx "]}, format="json"
        )

        assert len(response.data["invited"]) == 1
        assert correo.call_count == 1


@pytest.mark.django_db
class TestCorreoQueYaEsta:
    """Caso alternativo - Correo que ya está: no se manda una segunda."""

    def test_a_collaborator_is_not_invited_again(
        self, authenticated_client, user, correo
    ) -> None:
        miembro = MembershipFactory(account=user)

        response = authenticated_client.post(
            URL, {"emails": [miembro.user.email, "nuevo@obra.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["skipped"] == [
            {"email": miembro.user.email, "reason": "Ya es colaborador."}
        ]
        assert [i["email"] for i in response.data["invited"]] == ["nuevo@obra.mx"]
        assert correo.call_count == 1

    def test_a_pending_invitation_is_not_sent_twice(
        self, authenticated_client, user, correo
    ) -> None:
        InvitationFactory(account=user, email="ana@estudio.mx")

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["invited"] == []
        assert response.data["skipped"] == [
            {
                "email": "ana@estudio.mx",
                "reason": "Ya tiene una invitación pendiente; puedes reenviarla.",
            }
        ]
        correo.assert_not_called()

    def test_an_expired_invitation_is_sent_again(
        self, authenticated_client, user, correo
    ) -> None:
        """Caso de borde - Vencida: se reenvía con un enlace nuevo, no se duplica."""
        vieja = InvitationFactory(
            account=user,
            email="ana@estudio.mx",
            expires_at=timezone.now() - timedelta(days=1),
        )

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        vieja.refresh_from_db()
        assert Invitation.objects.count() == 1
        assert vieja.expires_at > timezone.now()
        assert vieja.token_hash == hash_token(enlaces(correo)[0])

    def test_another_company_inviting_the_same_person_is_fine(
        self, authenticated_client, correo
    ) -> None:
        """Una persona puede colaborar en varias empresas."""
        InvitationFactory(email="ana@estudio.mx")

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestCasosDeBorde:
    def test_your_own_email_is_not_invited(
        self, authenticated_client, user, correo
    ) -> None:
        response = authenticated_client.post(
            URL, {"emails": [user.email.upper()]}, format="json"
        )

        assert response.data["skipped"] == [
            {
                "email": user.email,
                "reason": "Es tu propio correo: ya eres el administrador.",
            }
        ]
        assert not Invitation.objects.exists()
        correo.assert_not_called()

    def test_a_malformed_email_stops_them_all(
        self, authenticated_client, correo
    ) -> None:
        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx", "luis@"]}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["emails"] == {
            "1": ["Revisa este correo: no parece válido."]
        }
        assert not Invitation.objects.exists()
        correo.assert_not_called()

    @pytest.mark.parametrize("emails", [[], [f"p{n}@obra.mx" for n in range(21)]])
    def test_between_one_and_twenty_at_a_time(
        self, authenticated_client, correo, emails
    ) -> None:
        response = authenticated_client.post(URL, {"emails": emails}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_without_a_session_nobody_is_invited(self, api_client, correo) -> None:
        response = api_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_mail_that_did_not_go_out_keeps_the_invitation(
        self, authenticated_client, correo
    ) -> None:
        """El administrador puede reenviarla: lo que falló fue el correo."""
        correo.return_value = False

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["invited"][0]["email_sent"] is False
        assert Invitation.objects.filter(status="pending").count() == 1
