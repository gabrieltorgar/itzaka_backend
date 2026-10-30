"""Lecturas de la configuración de folios."""

from apps.folios.codes import DocumentType, Mode
from apps.folios.models import FolioSetting
from apps.folios.services import preview_folio


def folio_setting_row(
    *, owner, document_type: str, setting: FolioSetting | None = None
) -> dict:
    """Lo que la pantalla muestra de un tipo: modalidad, clave y siguiente folio."""
    if setting is None:
        setting = FolioSetting.objects.filter(
            owner=owner, document_type=document_type
        ).first()
    mode = setting.mode if setting else Mode.AUTO
    prefix = setting.prefix if setting else ""
    return {
        "document_type": document_type,
        "label": str(DocumentType(document_type).label),
        "mode": mode,
        "prefix": prefix,
        "next_folio": preview_folio(
            owner=owner, mode=mode, prefix=prefix, document_type=document_type
        ),
    }


def folio_settings_for(*, owner) -> list[dict]:
    """Un renglón por tipo de documento, en el orden de ``DocumentType``.

    Los tipos que la empresa no ha configurado salen como «Autogenerado».
    """
    saved = {s.document_type: s for s in FolioSetting.objects.filter(owner=owner)}
    return [
        folio_setting_row(owner=owner, document_type=kind, setting=saved.get(kind))
        for kind in DocumentType.values
    ]
