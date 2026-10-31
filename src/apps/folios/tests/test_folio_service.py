"""Folios de documentos (iteracion-25 #2 · US-142): cómo se asigna el folio.

Dos modalidades por tipo de documento y por organización: «Autogenerado»
—un valor aleatorio con la forma de siempre, ``COT-1A2B3C4D``— y «Con clave»
—un prefijo de hasta 5 letras o números y un consecutivo, ``VEN-101``—. El
folio lo asigna el servidor al crear el documento y queda guardado: cambiar
la modalidad no toca lo ya creado. Es único dentro de la organización
(también entre tipos que comparten clave), y el contador de una clave nunca
se reinicia ni se reutiliza.
"""

import random
import re
import threading
import time

import pytest
from django.db import OperationalError, connections
from rest_framework.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.folios import services
from apps.folios.codes import DocumentType, Mode
from apps.folios.models import FolioCounter, IssuedFolio
from apps.folios.services import assign_folio, configure_folios, preview_folio

AUTO = re.compile(r"^COT-[0-9A-F]{8}$")


@pytest.fixture
def cuenta(db):
    return UserFactory()


@pytest.mark.django_db
class TestAutogenerado:
    def test_auto_mode_is_the_default_and_keeps_todays_shape(self, cuenta) -> None:
        """Flujo principal - Sin configurar, el folio es aleatorio como hoy."""
        folio = assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)

        assert AUTO.match(folio)
        assert IssuedFolio.objects.filter(owner=cuenta, folio=folio).exists()

    def test_each_document_type_keeps_its_own_auto_prefix(self, cuenta) -> None:
        prefixes = {
            assign_folio(owner=cuenta, document_type=kind).split("-")[0]
            for kind in DocumentType.values
        }

        assert prefixes == {"COT", "PRO", "REC", "PAG"}

    def test_auto_folio_retries_on_collision(self, cuenta, monkeypatch) -> None:
        """Caso de borde - El aleatorio que ya existe se vuelve a sortear."""
        IssuedFolio.objects.create(
            owner=cuenta, folio="COT-AAAAAAAA", document_type=DocumentType.QUOTE
        )
        draws = iter(["AAAAAAAA", "BBBBBBBB"])
        monkeypatch.setattr(services, "random_suffix", lambda: next(draws))

        folio = assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)

        assert folio == "COT-BBBBBBBB"


@pytest.mark.django_db
class TestConClave:
    def test_sequential_mode_numbers_from_one(self, cuenta) -> None:
        """Flujo principal - La clave y el consecutivo: VEN-1, VEN-2, VEN-3."""
        configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="VEN",
        )

        folios = [
            assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)
            for _ in range(3)
        ]

        assert folios == ["VEN-1", "VEN-2", "VEN-3"]

    def test_folio_is_unique_per_organization_not_global(self, cuenta) -> None:
        """Flujo principal - Dos organizaciones tienen su VEN-1; una sola, no dos."""
        otra = UserFactory()
        for owner in (cuenta, otra):
            configure_folios(
                owner=owner,
                document_type=DocumentType.QUOTE,
                mode=Mode.SEQUENTIAL,
                prefix="VEN",
            )

        mine = assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)
        theirs = assign_folio(owner=otra, document_type=DocumentType.QUOTE)

        assert mine == theirs == "VEN-1"
        with pytest.raises(Exception):  # noqa: B017 — la restricción única de la base
            IssuedFolio.objects.create(
                owner=cuenta, folio="VEN-1", document_type=DocumentType.PAYMENT
            )

    def test_prefix_counter_never_resets_when_reused(self, cuenta) -> None:
        """Caso de borde - Volver a VEN sigue donde se quedó: VEN-101, nunca VEN-1."""
        configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="VEN",
        )
        for _ in range(100):
            assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)
        configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="OBR",
        )
        assert assign_folio(owner=cuenta, document_type=DocumentType.QUOTE) == "OBR-1"
        configure_folios(
            owner=cuenta, document_type=DocumentType.QUOTE, mode=Mode.AUTO, prefix=""
        )
        assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)

        configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="VEN",
        )

        assert assign_folio(owner=cuenta, document_type=DocumentType.QUOTE) == "VEN-101"

    def test_document_types_sharing_a_prefix_share_the_counter(self, cuenta) -> None:
        """Caso de borde - Tipos con la misma clave no repiten número."""
        for kind in (DocumentType.QUOTE, DocumentType.PAYMENT):
            configure_folios(
                owner=cuenta, document_type=kind, mode=Mode.SEQUENTIAL, prefix="VEN"
            )

        quote = assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)
        payment = assign_folio(owner=cuenta, document_type=DocumentType.PAYMENT)

        assert (quote, payment) == ("VEN-1", "VEN-2")

    def test_sequential_skips_a_number_already_taken(self, cuenta) -> None:
        """Caso de borde - Un folio que ya existe (un documento anterior) se salta."""
        IssuedFolio.objects.create(
            owner=cuenta, folio="VEN-2", document_type=DocumentType.PAYMENT
        )
        configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="VEN",
        )

        folios = [
            assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)
            for _ in range(2)
        ]

        assert folios == ["VEN-1", "VEN-3"]
        assert FolioCounter.objects.get(owner=cuenta, prefix="VEN").last_number == 3

    def test_changing_the_mode_keeps_existing_folios(self, cuenta) -> None:
        """Caso de borde - Cambiar la modalidad no cambia los folios ya asignados."""
        before = assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)
        configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="VEN",
        )
        after = assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)

        assert AUTO.match(before)
        assert after == "VEN-1"
        assert set(IssuedFolio.objects.values_list("folio", flat=True)) == {
            before,
            after,
        }


@pytest.mark.django_db
class TestLaClave:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("ven", "VEN"), (" obr1 ", "OBR1"), ("A", "A"), ("12345", "12345")],
    )
    def test_prefix_is_normalized(self, cuenta, raw, expected) -> None:
        setting = configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix=raw,
        )

        assert setting.prefix == expected

    @pytest.mark.parametrize("raw", ["", "VENTAS", "VE-N", "VÉN", "V N"])
    def test_prefix_is_validated_on_the_server(self, cuenta, raw) -> None:
        """Caso alternativo - Una clave vacía, larga o con símbolos no se guarda."""
        with pytest.raises(ValidationError) as error:
            configure_folios(
                owner=cuenta,
                document_type=DocumentType.QUOTE,
                mode=Mode.SEQUENTIAL,
                prefix=raw,
            )

        assert "prefix" in error.value.detail

    def test_auto_mode_forgets_the_prefix(self, cuenta) -> None:
        setting = configure_folios(
            owner=cuenta, document_type=DocumentType.QUOTE, mode=Mode.AUTO, prefix="VEN"
        )

        assert setting.prefix == ""


@pytest.mark.django_db
class TestVistaPrevia:
    def test_preview_shows_the_next_folio_without_spending_it(self, cuenta) -> None:
        configure_folios(
            owner=cuenta,
            document_type=DocumentType.QUOTE,
            mode=Mode.SEQUENTIAL,
            prefix="VEN",
        )
        assign_folio(owner=cuenta, document_type=DocumentType.QUOTE)

        assert (
            preview_folio(owner=cuenta, mode=Mode.SEQUENTIAL, prefix="ven") == "VEN-2"
        )
        assert (
            preview_folio(owner=cuenta, mode=Mode.SEQUENTIAL, prefix="ven") == "VEN-2"
        )
        assert (
            preview_folio(owner=cuenta, mode=Mode.SEQUENTIAL, prefix="NUEVA")
            == "NUEVA-1"
        )

    def test_preview_of_auto_shows_the_shape(self, cuenta) -> None:
        preview = preview_folio(
            owner=cuenta, mode=Mode.AUTO, prefix="", document_type=DocumentType.PROJECT
        )

        assert re.match(r"^PRO-[0-9A-F]{8}$", preview)


@pytest.mark.django_db(transaction=True)
def test_concurrent_documents_never_share_a_folio() -> None:
    """Caso de borde - Dos documentos creados a la vez nunca comparten folio.

    Corre en hilos con su propia conexión. En PostgreSQL (CI) el contador se
    bloquea con ``select_for_update`` y los hilos esperan su turno; la SQLite
    en memoria de las pruebas locales no espera un candado (``database table
    is locked``), así que el hilo reintenta: lo que se prueba es que ningún
    folio se repita ni se salte.
    """
    owner = UserFactory()
    configure_folios(
        owner=owner,
        document_type=DocumentType.QUOTE,
        mode=Mode.SEQUENTIAL,
        prefix="VEN",
    )
    workers = 8
    start = threading.Barrier(workers)
    folios: list[str] = []
    errors: list[BaseException] = []

    def create() -> None:
        try:
            start.wait()
            for _ in range(500):
                try:
                    folios.append(
                        assign_folio(owner=owner, document_type=DocumentType.QUOTE)
                    )
                    return
                except OperationalError as exc:  # sólo SQLite: no espera candados
                    if "locked" not in str(exc):
                        raise
                    time.sleep(random.uniform(0.002, 0.02))  # noqa: S311 — espera, no secreto
            raise AssertionError("el hilo no consiguió turno")
        except BaseException as exc:  # noqa: BLE001 — se reporta en el hilo principal
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=create) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert sorted(folios, key=lambda f: int(f.split("-")[1])) == [
        f"VEN-{n}" for n in range(1, workers + 1)
    ]
