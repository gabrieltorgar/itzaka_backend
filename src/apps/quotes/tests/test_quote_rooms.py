"""RED tests for iteracion-31 #1 — habitaciones de la cotización a mano.

US-10, US-11 y US-12.

Hasta ahora sólo la cotización que sale del plano sabía de habitaciones: cada
partida medida guardaba cuánto de ella cae en cada una. Ahora la cotización tiene
su apartado «Habitaciones» —guardado con ella, en su orden, aunque una no tenga
servicios— y cada partida agregada a mano va en una habitación, entera, o en
«Sin habitación». Lo que midió el plano conserva su reparto, y sus habitaciones
también son de la cotización.
"""

import json
from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.planner.models import Plan
from apps.quotes.models import (
    MAX_ROOMS_PER_QUOTE,
    ROOM_NAME_MAX_LENGTH,
    Quote,
    QuoteRoom,
)

QUOTES_URL = "/api/quotes/"


def detail_url(quote_id) -> str:
    return f"{QUOTES_URL}{quote_id}/"


def sync_url(quote_id) -> str:
    return f"{QUOTES_URL}{quote_id}/plan-sync/"


@pytest.fixture
def obra(user):
    return {
        "client": ClientFactory(owner=user, name="Constructora Reyes"),
        "muro": TariffFactory(owner=user, name="Muro de block", unit_price="350"),
        "piso": TariffFactory(owner=user, name="Piso cerámico", unit_price="420"),
        "plan": Plan.objects.create(owner=user, name="Casa Pérez", document={}),
    }


def line(tariff, quantity: str, room: str | None = None, **extra) -> dict:
    """Una partida agregada a mano, entera en ``room`` (o sin habitación)."""
    data = {"tariff": str(tariff.id), "quantity": quantity, **extra}
    if room is not None:
        data["rooms"] = [{"name": room, "quantity": quantity}]
    return data


def rooms(*names: str) -> list[dict]:
    return [{"name": name} for name in names]


def payload(obra, items, room_names=None, **extra) -> dict:
    data = {"client": str(obra["client"].id), "items": items, **extra}
    if room_names is not None:
        data["rooms"] = rooms(*room_names)
    return data


def room_names(body: dict) -> list[str]:
    return [room["name"] for room in body["rooms"]]


def item_rooms(body: dict) -> list[list[tuple[str, str]]]:
    return [
        [(room["name"], room["quantity"]) for room in item["rooms"]]
        for item in body["items"]
    ]


# --- Escenarios del armador (US-10) ---


@pytest.mark.django_db
def test_rooms_are_saved_in_their_order_even_without_services(
    authenticated_client, obra
):
    """Flujo principal - Las habitaciones de la cotización (US-10)."""
    response = authenticated_client.post(
        QUOTES_URL,
        payload(obra, [line(obra["muro"], "5")], ["Cocina", "Baño"]),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert room_names(response.data) == ["Cocina", "Baño"]
    quote = Quote.objects.get(pk=response.data["id"])
    assert list(quote.rooms.values_list("name", flat=True)) == ["Cocina", "Baño"]
    fetched = authenticated_client.get(detail_url(quote.pk))
    assert room_names(fetched.data) == ["Cocina", "Baño"]


@pytest.mark.django_db
def test_each_line_goes_whole_in_its_room(authenticated_client, obra):
    """Flujo principal - Cada servicio en su habitación (US-10)."""
    response = authenticated_client.post(
        QUOTES_URL,
        payload(
            obra,
            [line(obra["muro"], "12", "Cocina"), line(obra["muro"], "8", "Baño")],
            ["Cocina", "Baño"],
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert item_rooms(response.data) == [
        [("Cocina", "12.00")],
        [("Baño", "8.00")],
    ]
    assert response.data["total"] == Decimal("7000")


@pytest.mark.django_db
def test_a_line_without_room_and_a_quote_without_rooms(authenticated_client, obra):
    """Caso alternativo - Un servicio sin habitación (US-10)."""
    with_rooms = authenticated_client.post(
        QUOTES_URL,
        payload(obra, [line(obra["piso"], "3")], ["Cocina"]),
        format="json",
    )
    without = authenticated_client.post(
        QUOTES_URL, payload(obra, [line(obra["piso"], "3")]), format="json"
    )

    assert with_rooms.status_code == status.HTTP_201_CREATED, with_rooms.data
    assert item_rooms(with_rooms.data) == [[]]
    assert without.status_code == status.HTTP_201_CREATED, without.data
    assert without.data["rooms"] == []
    assert item_rooms(without.data) == [[]]


@pytest.mark.django_db
def test_rooms_a_line_uses_join_the_quote_even_if_not_listed(
    authenticated_client, obra
):
    """Una habitación que usa una partida entra al apartado aunque no venga."""
    response = authenticated_client.post(
        QUOTES_URL,
        payload(obra, [line(obra["muro"], "4", "Sala")], ["Cocina"]),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert room_names(response.data) == ["Cocina", "Sala"]


# --- Editar (US-11) ---


def create(authenticated_client, obra, items, names=None) -> dict:
    response = authenticated_client.post(
        QUOTES_URL, payload(obra, items, names), format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return response.data


@pytest.mark.django_db
def test_renaming_a_room_moves_its_lines(authenticated_client, obra):
    """Caso de borde - Renombrar o quitar una habitación: renombrar (US-11)."""
    quote = create(
        authenticated_client,
        obra,
        [line(obra["muro"], "12", "Cocina"), line(obra["piso"], "6", "Cocina")],
        ["Cocina", "Baño"],
    )

    response = authenticated_client.put(
        detail_url(quote["id"]),
        payload(
            obra,
            [
                line(obra["muro"], "12", "Cocina integral"),
                line(obra["piso"], "6", "Cocina integral"),
            ],
            ["Cocina integral", "Baño"],
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    assert room_names(response.data) == ["Cocina integral", "Baño"]
    assert item_rooms(response.data) == [
        [("Cocina integral", "12.00")],
        [("Cocina integral", "6.00")],
    ]


@pytest.mark.django_db
def test_removing_a_room_leaves_its_lines_without_room(authenticated_client, obra):
    """Caso de borde - Renombrar o quitar una habitación: quitar (US-11)."""
    quote = create(
        authenticated_client,
        obra,
        [line(obra["muro"], "12", "Cocina"), line(obra["piso"], "6", "Baño")],
        ["Cocina", "Baño"],
    )

    response = authenticated_client.put(
        detail_url(quote["id"]),
        payload(
            obra,
            [line(obra["muro"], "12"), line(obra["piso"], "6", "Baño")],
            ["Baño"],
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    assert room_names(response.data) == ["Baño"]
    assert item_rooms(response.data) == [[], [("Baño", "6.00")]]
    assert len(response.data["items"]) == 2


@pytest.mark.django_db
def test_an_older_screen_that_does_not_send_rooms_keeps_them(
    authenticated_client, obra
):
    """Sin el apartado en la petición, la cotización conserva sus habitaciones."""
    quote = create(
        authenticated_client, obra, [line(obra["muro"], "2")], ["Cocina", "Baño"]
    )

    response = authenticated_client.put(
        detail_url(quote["id"]),
        payload(obra, [line(obra["muro"], "3")]),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    assert room_names(response.data) == ["Cocina", "Baño"]


@pytest.mark.django_db
def test_plan_lines_keep_their_split_and_their_rooms_are_listed(
    authenticated_client, obra
):
    """Caso de borde - Lo que midió el plano no se toca (US-11)."""
    measured = {
        "tariff": str(obra["muro"].id),
        "quantity": "20",
        "from_plan": True,
        "rooms": [
            {"name": "Recámara", "quantity": "12"},
            {"name": "Baño", "quantity": "8"},
        ],
    }
    quote = authenticated_client.post(
        QUOTES_URL,
        {
            "client": str(obra["client"].id),
            "plan": str(obra["plan"].id),
            "items": [measured],
        },
        format="json",
    ).data
    # Las habitaciones del plano están en el apartado para elegirlas.
    assert sorted(room_names(quote)) == ["Baño", "Recámara"]

    response = authenticated_client.put(
        detail_url(quote["id"]),
        payload(
            obra,
            [
                {"tariff": str(obra["muro"].id), "quantity": "20"},
                line(obra["piso"], "9", "Recámara"),
            ],
            ["Baño", "Recámara", "Cocina"],
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    assert room_names(response.data) == ["Baño", "Recámara", "Cocina"]
    assert item_rooms(response.data) == [
        [("Baño", "8.00"), ("Recámara", "12.00")],
        [("Recámara", "9.00")],
    ]


@pytest.mark.django_db
def test_resyncing_from_the_plan_adds_its_rooms_once(authenticated_client, obra):
    """Caso de borde - Volver a cotizar desde el plano (US-11)."""
    quote = create(
        authenticated_client, obra, [line(obra["piso"], "6", "Cocina")], ["Cocina"]
    )

    response = authenticated_client.post(
        sync_url(quote["id"]),
        {
            "plan": str(obra["plan"].id),
            "items": [
                {
                    "tariff": str(obra["muro"].id),
                    "quantity": "20",
                    "rooms": [
                        {"name": "cocina", "quantity": "5"},
                        {"name": "Sala", "quantity": "15"},
                    ],
                }
            ],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    assert room_names(response.data) == ["Cocina", "Sala"]
    piso = next(i for i in response.data["items"] if i["name"] == "Piso cerámico")
    assert piso["rooms"] == [{"name": "Cocina", "quantity": "6.00"}]


# --- Validación (VAL-01) ---


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("names", "message"),
    [
        (["Cocina", "  "], "Escribe el nombre de la habitación"),
        (
            ["x" * (ROOM_NAME_MAX_LENGTH + 1)],
            "El nombre de la habitación no puede pasar de "
            f"{ROOM_NAME_MAX_LENGTH} caracteres",
        ),
        (["Cocina", " cocina "], "Esa habitación ya está en la cotización"),
        (["Baño  2", "baño 2"], "Esa habitación ya está en la cotización"),
    ],
)
def test_invalid_room_names_are_rejected_on_their_row(
    authenticated_client, obra, names, message
):
    """VAL-01 · US-10 · Caso de borde - Nombres de habitación que no cuadran."""
    response = authenticated_client.post(
        QUOTES_URL, payload(obra, [line(obra["muro"], "2")], names), format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    rows = json.loads(response.content)["rooms"]
    last = str(len(names) - 1)
    assert set(rows) == {last}
    assert rows[last]["name"] == [message]
    assert not Quote.objects.exists()
    assert not QuoteRoom.objects.exists()


@pytest.mark.django_db
def test_too_many_rooms_are_rejected(authenticated_client, obra):
    """VAL-01 · US-10 · Caso de borde - más habitaciones de las que caben."""
    names = [f"Cuarto {n}" for n in range(MAX_ROOMS_PER_QUOTE + 1)]

    response = authenticated_client.post(
        QUOTES_URL, payload(obra, [line(obra["muro"], "2")], names), format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "rooms" in response.data
    assert not Quote.objects.exists()


@pytest.mark.django_db
def test_invalid_rooms_on_edit_change_nothing(authenticated_client, obra):
    """VAL-01 · US-11 · Un apartado inválido al editar no guarda nada."""
    quote = create(
        authenticated_client, obra, [line(obra["muro"], "2", "Cocina")], ["Cocina"]
    )

    response = authenticated_client.put(
        detail_url(quote["id"]),
        payload(obra, [line(obra["muro"], "9")], ["Sala", "sala"]),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    fetched = authenticated_client.get(detail_url(quote["id"])).data
    assert room_names(fetched) == ["Cocina"]
    assert item_rooms(fetched) == [[("Cocina", "2.00")]]


# --- Aislamiento (SEC-01) ---


@pytest.mark.django_db
def test_another_company_never_sees_the_rooms(authenticated_client, obra, user_factory):
    """SEC-01 · US-11 · Las habitaciones viajan con su cotización y nada más."""
    quote = create(authenticated_client, obra, [line(obra["muro"], "2")], ["Cocina"])
    other = user_factory()
    authenticated_client.force_authenticate(other)

    assert authenticated_client.get(detail_url(quote["id"])).status_code == 404
    listing = authenticated_client.get(QUOTES_URL).data
    assert listing["count"] == 0
