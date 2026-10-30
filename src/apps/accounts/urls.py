"""Accounts (auth) URLs. Endpoints are added per user story via TDD."""

from django.urls import path

from apps.accounts.views import (
    CsrfCookieView,
    LoginView,
    LogoutView,
    MyAccountDeleteView,
    MyAccountView,
    MyEmailResendView,
    MyEmailVerifyView,
    MyEmailView,
    MyOrganizationLogoView,
    MyOrganizationView,
    MyPasswordView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendOtpView,
    SessionRefreshView,
    VerifyOtpView,
)

app_name = "accounts"

urlpatterns = [
    path("csrf/", CsrfCookieView.as_view(), name="csrf"),
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-otp/", VerifyOtpView.as_view(), name="verify-otp"),
    path("resend-otp/", ResendOtpView.as_view(), name="resend-otp"),
    path("login/", LoginView.as_view(), name="login"),
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("me/", MyAccountView.as_view(), name="me"),
    path("me/email/", MyEmailView.as_view(), name="me-email"),
    path("me/email/verify/", MyEmailVerifyView.as_view(), name="me-email-verify"),
    path("me/email/resend/", MyEmailResendView.as_view(), name="me-email-resend"),
    path("me/password/", MyPasswordView.as_view(), name="me-password"),
    path("me/delete/", MyAccountDeleteView.as_view(), name="me-delete"),
    path("organization/", MyOrganizationView.as_view(), name="organization"),
    path(
        "organization/logo/",
        MyOrganizationLogoView.as_view(),
        name="organization-logo",
    ),
    # La sesión vive en cookies HttpOnly: renovarla (rota el refresh) y cerrarla.
    path("refresh/", SessionRefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
