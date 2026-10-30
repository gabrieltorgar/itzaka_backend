"""Tests for the session refresh endpoint (silent session renewal).

A valid refresh must yield a fresh access so an active session is never dropped
when the short-lived access expires. Since iteracion-12 both travel in HttpOnly
cookies; a client that still sends the refresh in the body is served too.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"


@pytest.mark.django_db
class TestTokenRefresh:
    """POST /api/auth/refresh/ exchanges the refresh for a new session."""

    def test_valid_refresh_cookie_renews_the_session(
        self, api_client, user_factory
    ) -> None:
        """The refresh cookie set at login yields new session cookies."""
        account = user_factory(is_email_verified=True, password="testpass123")
        api_client.post(LOGIN_URL, {"email": account.email, "password": "testpass123"})

        response = api_client.post(REFRESH_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies["itzaka_access"].value
        assert "access" not in response.data

    def test_a_refresh_sent_in_the_body_still_works(
        self, api_client, user_factory
    ) -> None:
        """An API client without cookies can renew with the refresh in the body."""
        account = user_factory(is_email_verified=True, password="testpass123")
        login = api_client.post(
            LOGIN_URL, {"email": account.email, "password": "testpass123"}
        )
        refresh = login.cookies["itzaka_refresh"].value

        response = APIClient().post(REFRESH_URL, {"refresh": refresh})

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies["itzaka_access"].value

    def test_invalid_refresh_returns_401(self, api_client) -> None:
        """A bogus refresh token is rejected with 401."""
        response = api_client.post(REFRESH_URL, {"refresh": "not-a-real-token"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
