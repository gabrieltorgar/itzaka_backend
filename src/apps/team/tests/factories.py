"""Factories para colaboradores e invitaciones."""

from datetime import timedelta

import factory
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.team.models import Invitation, Membership
from apps.team.services import hash_token


class MembershipFactory(factory.django.DjangoModelFactory):
    """Una persona que colabora, activa, en la empresa de otra cuenta."""

    class Meta:
        model = Membership

    account = factory.SubFactory(UserFactory)
    user = factory.SubFactory(UserFactory, has_own_workspace=False)
    is_active = True


class InvitationFactory(factory.django.DjangoModelFactory):
    """Una invitación pendiente y vigente; su enlace es ``token``."""

    class Meta:
        model = Invitation
        exclude = ("token",)

    account = factory.SubFactory(UserFactory)
    email = factory.Sequence(lambda n: f"invitada{n:03d}@estudio.test")
    token = factory.Sequence(lambda n: f"enlace-de-prueba-{n:04d}")
    token_hash = factory.LazyAttribute(lambda o: hash_token(o.token))
    status = Invitation.Status.PENDING
    sent_at = factory.LazyFunction(timezone.now)
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
