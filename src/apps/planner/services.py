"""Planner writes that are more than saving the editor's document."""

import logging

from django.db import transaction
from django.db.models import QuerySet

from apps.planner.models import Plan
from common.bulk import BulkResult

logger = logging.getLogger(__name__)


def delete_plans(*, plans: QuerySet[Plan]) -> BulkResult:
    """Elimina varios planos de la cuenta (US-78 en lote, iteracion-17).

    Un plano nunca se niega a irse: las cotizaciones que salieron de él se
    quedan, sin el enlace. Uno por uno de todos modos, cada uno en su propio
    bloque atómico, para que el resultado cuente lo que de verdad se fue.
    """
    result = BulkResult()
    for plan in plans:
        result.requested += 1
        with transaction.atomic():
            plan.delete()
        result.processed += 1
    logger.info(
        "Plans deleted in bulk",
        extra={"requested": result.requested, "processed": result.processed},
    )
    return result
