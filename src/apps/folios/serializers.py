"""Folios serializers: lo que se lee y lo que se manda de la configuración."""

from rest_framework import serializers

from apps.folios.codes import PREFIX_MAX_LENGTH, DocumentType, Mode

#: Lo que puede llegar en la clave: con margen sobre los 5 para que «VENTAS»
#: llegue al servicio y reciba su mensaje, no uno genérico de longitud.
PREFIX_INPUT_MAX_LENGTH = PREFIX_MAX_LENGTH * 4


class FolioSettingSerializer(serializers.Serializer):
    """Un tipo de documento con su modalidad, su clave y el siguiente folio."""

    document_type = serializers.ChoiceField(
        choices=DocumentType.choices, read_only=True
    )
    label = serializers.CharField(read_only=True)
    mode = serializers.ChoiceField(choices=Mode.choices, read_only=True)
    prefix = serializers.CharField(read_only=True)
    next_folio = serializers.CharField(read_only=True)


class FolioSettingInputSerializer(serializers.Serializer):
    """La modalidad y la clave que elige el administrador.

    La clave se normaliza y se valida en el servicio (mayúsculas, 1 a 5 letras
    o números); aquí sólo se acota lo que puede llegar.
    """

    mode = serializers.ChoiceField(choices=Mode.choices)
    prefix = serializers.CharField(
        max_length=PREFIX_INPUT_MAX_LENGTH, required=False, allow_blank=True, default=""
    )


class FolioPreviewSerializer(serializers.Serializer):
    """Los parámetros de la vista previa: ``?mode=sequential&prefix=VEN``."""

    mode = serializers.ChoiceField(choices=Mode.choices, default=Mode.SEQUENTIAL)
    prefix = serializers.CharField(
        max_length=PREFIX_INPUT_MAX_LENGTH, required=False, allow_blank=True, default=""
    )
