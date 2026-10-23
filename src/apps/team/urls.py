"""Team URLs."""

from django.urls import path

from apps.team.views import (
    InvitationAcceptView,
    InvitationCancelView,
    InvitationDetailView,
    InvitationResendView,
    InvitationsView,
    MemberView,
    TeamBulkView,
    TeamView,
)

urlpatterns = [
    path("collaborators/", TeamView.as_view(), name="team"),
    path(
        "collaborators/bulk/<str:action>/",
        TeamBulkView.as_view(),
        name="team-bulk",
    ),
    path(
        "collaborators/members/<uuid:member_id>/",
        MemberView.as_view(),
        name="member",
    ),
    path("collaborators/invitations/", InvitationsView.as_view(), name="invitations"),
    path(
        "collaborators/invitations/<uuid:invitation_id>/resend/",
        InvitationResendView.as_view(),
        name="invitation-resend",
    ),
    path(
        "collaborators/invitations/<uuid:invitation_id>/cancel/",
        InvitationCancelView.as_view(),
        name="invitation-cancel",
    ),
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
