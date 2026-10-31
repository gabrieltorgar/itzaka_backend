"""Payments serializers (input validation + read shapes)."""

from rest_framework import serializers

from apps.payments.models import Payment
from apps.projects.models import Project
from apps.quotes.models import QuoteItem
from common.fields import OwnedPrimaryKeyRelatedField


class PaymentInputSerializer(serializers.Serializer):
    """Validates a payment payload."""

    project = OwnedPrimaryKeyRelatedField(
        queryset=Project.objects.all(), not_found="Proyecto no encontrado."
    )
    quote_item = OwnedPrimaryKeyRelatedField(
        queryset=QuoteItem.objects.all(),
        owner_field="quote__owner",
        not_found="Partida no encontrada.",
        required=False,
        allow_null=True,
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(
        choices=Payment.Method.choices,
        required=False,
        default=Payment.Method.CASH,
    )
    date = serializers.DateField()


class PaymentSerializer(serializers.ModelSerializer):
    """Read shape of a payment."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "folio",
            "project",
            "quote_item",
            "amount",
            "method",
            "date",
            "created_at",
        ]
