"""Los folios de los documentos que existían antes de iteracion-25.

El navegador los derivaba del id (``COT-`` y los primeros ocho caracteres) y
así quedaron impresos. Las migraciones que agregan el campo ``folio`` llaman a
:func:`backfill_legacy_folios` para guardar exactamente ese valor y apartarlo
en el registro de la empresa: los PDFs ya emitidos no cambian.

No se cambia este cálculo: lo leen migraciones ya aplicadas.
"""

from apps.folios.codes import legacy_folio

#: Si dos documentos viejos de la misma empresa empezaban igual (imprimían el
#: mismo folio), el segundo toma más caracteres de su id para no repetirlo.
LEGACY_LENGTHS = (8, 12, 32)


def backfill_legacy_folios(
    apps, *, app_label: str, model_name: str, document_type: str, prefix: str
) -> None:
    """Guarda en cada documento de ``app_label.model_name`` el folio que imprimía."""
    model = apps.get_model(app_label, model_name)
    issued = apps.get_model("folios", "IssuedFolio")
    taken = {
        (owner, folio)
        for owner, folio in issued.objects.values_list("owner_id", "folio")
    }
    for pk, owner_id in model.objects.order_by("created_at", "pk").values_list(
        "pk", "owner_id"
    ):
        for length in LEGACY_LENGTHS:
            folio = legacy_folio(prefix, pk, length)
            if (owner_id, folio) not in taken:
                break
        taken.add((owner_id, folio))
        model.objects.filter(pk=pk).update(folio=folio)
        issued.objects.create(
            owner_id=owner_id, folio=folio, document_type=document_type
        )
