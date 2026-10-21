"""Serializers de colaboradores e invitaciones."""

from rest_framework import serializers

#: Cuántos correos caben en una sola tanda.
MAX_EMAILS = 20


class InviteSerializer(serializers.Serializer):
    """Los correos a invitar: de uno a veinte."""

    emails = serializers.ListField(
        child=serializers.EmailField(
            error_messages={"invalid": "Revisa este correo: no parece válido."}
        ),
        min_length=1,
        max_length=MAX_EMAILS,
        error_messages={
            "min_length": "Escribe al menos un correo.",
            "max_length": f"Invita hasta {MAX_EMAILS} correos a la vez.",
        },
    )


class SentInvitationSerializer(serializers.Serializer):
    """Una invitación que acaba de salir, y si su correo llegó a enviarse."""

    id = serializers.UUIDField(source="invitation.id")
    email = serializers.EmailField(source="invitation.email")
    expires_at = serializers.DateTimeField(source="invitation.expires_at")
    email_sent = serializers.BooleanField()


class SkippedSerializer(serializers.Serializer):
    email = serializers.EmailField()
    reason = serializers.CharField()


class InviteResultSerializer(serializers.Serializer):
    invited = SentInvitationSerializer(many=True)
    skipped = SkippedSerializer(many=True)
