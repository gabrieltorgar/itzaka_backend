"""Teléfonos validados y en un solo formato (iteracion-13 #3).

Se guardan en E.164 (+525512345678) con ``PhoneNumberField`` y se leen como los
escribiría una persona en México: los de México sin la lada del país
(55 1234 5678) y los de fuera con la suya (+1 212-555-0123).
"""

import phonenumbers
from phonenumber_field.serializerfields import PhoneNumberField

HOME_REGION = "MX"
INVALID = "Escribe un teléfono válido, con su lada."


def display(value) -> str:
    """Cómo se lee un teléfono guardado; uno que no se pudo leer, como llegó."""
    if not value:
        return ""
    if not value.is_valid():
        return value.raw_input or ""
    national = phonenumbers.region_code_for_number(value) == HOME_REGION
    return phonenumbers.format_number(
        value,
        phonenumbers.PhoneNumberFormat.NATIONAL
        if national
        else phonenumbers.PhoneNumberFormat.INTERNATIONAL,
    )


class PhoneField(PhoneNumberField):
    """Un teléfono opcional: vacío vale, uno que no es teléfono no."""

    default_error_messages = {"invalid": INVALID}

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        super().__init__(**kwargs)

    def to_representation(self, value) -> str:
        return display(value)


def normalize_existing(model, field: str) -> int:
    """Pasa a E.164 los teléfonos guardados que se pueden leer.

    Los que no —un «ext. 12», una nota— se quedan como estaban: se ven igual y
    sólo se piden bien la próxima vez que se editen. Devuelve cuántos cambió.
    """
    changed = 0
    for pk, raw in model.objects.exclude(**{field: ""}).values_list("pk", field):
        try:
            parsed = phonenumbers.parse(str(raw), HOME_REGION)
        except phonenumbers.NumberParseException:
            continue
        if not phonenumbers.is_valid_number(parsed):
            continue
        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        if str(raw) != e164:
            model.objects.filter(pk=pk).update(**{field: e164})
            changed += 1
    return changed
