"""reCAPTCHA v3 y honeypot en los formularios públicos (bug iteracion-12 #4).

US-83 · US-01 · US-82. Registro, acceso, recuperación y contacto llevan un token
de reCAPTCHA que el servidor verifica con Google, y un campo trampa («website»)
que una persona nunca ve. Si Google no contesta, las puertas de la cuenta se
cierran (503) y el contacto se acepta marcado para revisar.
"""

import json
from urllib.error import URLError

import pytest
from rest_framework import status

import core.settings as core_settings
from apps.accounts.models import User
from apps.leads.models import Lead
from apps.legal.tests.consent import accepted
from common import recaptcha
from common.recaptcha import CaptchaUnavailable, verify_recaptcha

HUMANO = {
    "success": True,
    "action": "contact_submit",
    "hostname": "cuotreka.vercel.app",
    "score": 0.9,
}


@pytest.fixture
def captcha(settings, mocker):
    """reCAPTCHA encendido, con la respuesta de Google en las manos de la prueba."""
    settings.RECAPTCHA_ENABLED = True
    settings.RECAPTCHA_SECRET_KEY = "secreta"
    settings.RECAPTCHA_MIN_SCORE = 0.5
    settings.RECAPTCHA_HOSTNAMES = ["cuotreka.vercel.app"]
    return mocker.patch.object(recaptcha, "_siteverify")


def google_dice(captcha, **cambios):
    def responder(*, token, remote_ip):
        return {**HUMANO, **cambios}

    captcha.side_effect = responder


class TestVerificarConGoogle:
    """La respuesta de Google se lee entera: éxito, acción, dominio y puntaje."""

    def test_a_human_passes(self, captcha) -> None:
        google_dice(captcha)

        result = verify_recaptcha(token="t", action="contact_submit", remote_ip=None)

        assert result.ok

    @pytest.mark.parametrize(
        ("cambio", "motivo"),
        [
            ({"success": False}, "invalid"),
            ({"action": "otra_cosa"}, "action"),
            ({"hostname": "sitio-ajeno.com"}, "hostname"),
            ({"score": 0.1}, "score"),
        ],
    )
    def test_each_check_can_stop_it(self, captcha, cambio, motivo) -> None:
        google_dice(captcha, **cambio)

        result = verify_recaptcha(token="t", action="contact_submit", remote_ip=None)

        assert (result.ok, result.reason) == (False, motivo)

    def test_without_a_token_google_is_not_even_asked(self, captcha) -> None:
        result = verify_recaptcha(token="", action="contact_submit", remote_ip=None)

        assert (result.ok, result.reason) == (False, "missing")
        captcha.assert_not_called()

    def test_google_down_is_its_own_case(self, captcha) -> None:
        captcha.side_effect = CaptchaUnavailable

        with pytest.raises(CaptchaUnavailable):
            verify_recaptcha(token="t", action="contact_submit", remote_ip=None)

    def test_disabled_it_lets_everything_through(self, settings, mocker) -> None:
        settings.RECAPTCHA_ENABLED = False
        llamada = mocker.patch.object(recaptcha, "_siteverify")

        assert verify_recaptcha(token=None, action="x", remote_ip=None).ok
        llamada.assert_not_called()

    def test_the_http_call_reads_googles_json(self, settings, mocker) -> None:
        settings.RECAPTCHA_SECRET_KEY = "secreta"
        respuesta = mocker.MagicMock()
        respuesta.__enter__.return_value.read.return_value = json.dumps(HUMANO).encode()
        abrir = mocker.patch.object(recaptcha, "urlopen", return_value=respuesta)

        assert recaptcha._siteverify(token="t", remote_ip="1.2.3.4") == HUMANO
        assert abrir.call_args.kwargs["timeout"] == 5

    def test_an_unreachable_google_is_unavailable(self, settings, mocker) -> None:
        mocker.patch.object(recaptcha, "urlopen", side_effect=URLError("caído"))

        with pytest.raises(CaptchaUnavailable):
            recaptcha._siteverify(token="t", remote_ip=None)


class TestEncendidoConLaLlave:
    """Sin llave secreta no se verifica: así no se cierra la puerta sin llaves."""

    def test_it_follows_the_secret_key(self) -> None:
        assert core_settings.RECAPTCHA_ENABLED is bool(
            core_settings.RECAPTCHA_SECRET_KEY
        )


REGISTRO = {
    "email": "nueva@estudio.mx",
    "password": "Segura-12345",
    "terms_version": None,
    "privacy_version": None,
}


@pytest.fixture
def registro(db):
    return {**REGISTRO, **accepted()}


@pytest.mark.django_db
class TestPoliticaPorFormulario:
    """Qué hace cada formulario con un bot, con un token malo y sin Google."""

    def test_signup_with_a_low_score_is_refused(
        self, api_client, captcha, registro
    ) -> None:
        google_dice(captcha, action="signup_submit", score=0.1)

        response = api_client.post(
            "/api/auth/register/", {**registro, "recaptcha_token": "t"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not User.objects.filter(email="nueva@estudio.mx").exists()

    def test_signup_with_a_human_goes_through(
        self, api_client, captcha, registro
    ) -> None:
        google_dice(captcha, action="signup_submit")

        response = api_client.post(
            "/api/auth/register/", {**registro, "recaptcha_token": "t"}
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert captcha.call_args.kwargs["token"] == "t"

    @pytest.mark.parametrize(
        ("url", "payload"),
        [
            ("/api/auth/login/", {"email": "a@b.mx", "password": "x"}),
            ("/api/auth/password-reset/", {"email": "a@b.mx"}),
        ],
    )
    def test_without_a_token_the_account_doors_stay_shut(
        self, api_client, captcha, url, payload
    ) -> None:
        response = api_client.post(url, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No pudimos verificar" in str(response.data)

    @pytest.mark.parametrize(
        ("url", "payload"),
        [
            ("/api/auth/login/", {"email": "a@b.mx", "password": "x"}),
            ("/api/auth/password-reset/", {"email": "a@b.mx"}),
            ("/api/auth/register/", REGISTRO),
        ],
    )
    def test_with_google_down_the_account_doors_answer_503(
        self, api_client, captcha, url, payload
    ) -> None:
        captcha.side_effect = CaptchaUnavailable

        response = api_client.post(url, {**payload, "recaptcha_token": "t"})

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_with_google_down_contact_is_kept_for_review(
        self, api_client, captcha
    ) -> None:
        captcha.side_effect = CaptchaUnavailable

        response = api_client.post(
            "/api/contact/",
            {"name": "Ana", "email": "ana@correo.mx", "recaptcha_token": "t"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Lead.objects.get().needs_review is True

    def test_a_verified_contact_needs_no_review(self, api_client, captcha) -> None:
        google_dice(captcha)

        api_client.post(
            "/api/contact/",
            {"name": "Ana", "email": "ana@correo.mx", "recaptcha_token": "t"},
        )

        assert Lead.objects.get().needs_review is False


@pytest.mark.django_db
class TestCampoTrampa:
    """Un bot que llena «website» recibe la respuesta de siempre y nada pasa."""

    def test_contact_bot_is_dropped_silently(self, api_client, captcha) -> None:
        response = api_client.post(
            "/api/contact/",
            {"name": "Bot", "email": "bot@spam.mx", "website": "http://spam"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert not Lead.objects.exists()
        captcha.assert_not_called()

    def test_signup_bot_gets_no_account(self, api_client, captcha, registro) -> None:
        response = api_client.post(
            "/api/auth/register/", {**registro, "website": "http://spam"}
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "nueva@estudio.mx"
        assert not User.objects.filter(email="nueva@estudio.mx").exists()

    def test_password_reset_bot_gets_the_usual_answer(
        self, api_client, captcha, user, mocker
    ) -> None:
        enviar = mocker.patch("apps.accounts.services.send_verification_code")

        response = api_client.post(
            "/api/auth/password-reset/", {"email": user.email, "website": "x"}
        )

        assert response.status_code == status.HTTP_200_OK
        enviar.assert_not_called()

    def test_login_bot_never_gets_a_session(self, api_client, captcha) -> None:
        cuenta = User.objects.create_user(email="ana@estudio.mx", password="Bien-123")
        cuenta.is_email_verified = True
        cuenta.save()

        response = api_client.post(
            "/api/auth/login/",
            {"email": "ana@estudio.mx", "password": "Bien-123", "website": "x"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "cuotreka_access" not in response.cookies
