"""Team URLs."""

from django.urls import path

from apps.team.views import (
    InvitationAcceptView,
    InvitationDetailView,
    InvitationsView,
)

urlpatterns = [
    path("collaborators/invitations/", InvitationsView.as_view(), name="invitations"),
    path(
        "invitations/<str:token>/",
        InvitationDetailView.as_view(),
        name="invitation-detail",
    ),
    path(
        "invitations/<str:token>/accept/",
        InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
]
