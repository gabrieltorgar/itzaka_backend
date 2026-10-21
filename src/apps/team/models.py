"""Colaboradores: quién trabaja en la empresa de quién, y las invitaciones.

La empresa es la cuenta de quien la creó —su administrador—: los datos de
trabajo cuelgan de ella (``owner``) y un colaborador trabaja sobre esos mismos
datos. Una persona puede colaborar en varias empresas.
"""

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


class Membership(models.Model):
    """Una persona que trabaja en la empresa de otra cuenta."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name=_("empresa"),
        help_text=_("La cuenta del administrador, dueña de los datos."),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("colaborador"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("activo"),
        help_text=_("Desactivado, no entra a la empresa hasta que lo activen."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("desde"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("actualizado en"))

    class Meta:
        db_table = "team_membership"
        verbose_name = _("colaborador")
        verbose_name_plural = _("colaboradores")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "user"], name="team_membership_once_per_company"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} en {self.account}"


class Invitation(models.Model):
    """Un enlace por correo para sumarse a una empresa.

    El enlace lleva un secreto que sólo conoce quien recibió el correo; aquí
    queda su huella (SHA-256), nunca el secreto.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        ACCEPTED = "accepted", _("Aceptada")
        CANCELLED = "cancelled", _("Cancelada")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name=_("empresa"),
    )
    email = models.EmailField(verbose_name=_("correo invitado"))
    token_hash = models.CharField(
        max_length=64, unique=True, editable=False, verbose_name=_("huella del enlace")
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("estado"),
    )
    sent_at = models.DateTimeField(verbose_name=_("enviada"))
    expires_at = models.DateTimeField(verbose_name=_("vence"))
    accepted_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("aceptada")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creada"))

    class Meta:
        db_table = "team_invitation"
        verbose_name = _("invitación")
        verbose_name_plural = _("invitaciones")
        ordering = ["-sent_at"]
        constraints = [
            # Una sola pendiente por correo y empresa: la segunda es un reenvío.
            models.UniqueConstraint(
                fields=["account", "email"],
                condition=Q(status="pending"),
                name="team_invitation_one_pending",
            )
        ]

    def __str__(self) -> str:
        return f"{self.email} → {self.account} ({self.get_status_display()})"

    @property
    def is_expired(self) -> bool:
        return self.status == self.Status.PENDING and self.expires_at <= timezone.now()
