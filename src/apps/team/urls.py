"""Team URLs."""

from django.urls import path

from apps.team.views import InvitationsView

urlpatterns = [
    path("collaborators/invitations/", InvitationsView.as_view(), name="invitations"),
]
