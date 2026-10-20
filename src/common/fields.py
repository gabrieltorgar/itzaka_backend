"""Campos de entrada acotados a la cuenta de quien escribe (iteracion-12 #2)."""

from rest_framework import serializers


class OwnedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Un id que sólo encuentra registros de la cuenta de quien escribe.

    Un registro de otra cuenta no existe para quien lo pide: se rechaza con el
    mismo mensaje que un id que no es de nadie, para que la respuesta no delate
    qué hay en otras cuentas. El servicio vuelve a revisar la propiedad; esta es
    la primera barrera, no la única.

    Necesita la petición en el contexto del serializer; sin ella no encuentra
    nada.
    """

    def __init__(self, *, owner_field: str = "owner", not_found: str, **kwargs):
        self.owner_field = owner_field
        kwargs.setdefault("error_messages", {})
        kwargs["error_messages"].setdefault("does_not_exist", not_found)
        kwargs["error_messages"].setdefault("incorrect_type", not_found)
        super().__init__(**kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return queryset.none()
        return queryset.filter(**{self.owner_field: user})
