"""RED tests for iteracion-25 #1 — el desglose por habitación (US-12, US-95).

El documento de la cotización sólo tenía el resumen global: una partida por
servicio con la cantidad sumada de todo el plano. Ahora cada partida que mide el
plano guarda cuánto de ella cae en cada habitación, para que el documento la
desglose por habitación. Es un dato más de la partida: el resumen global, sus
cantidades y su total no cambian.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.planner.models import Plan
from apps.quotes.models import (
    MAX_ROOMS_PER_ITEM,
    ROOM_NAME_MAX_LENGTH,
    Quote,
    QuoteItemRoom,
)

QUOTES_URL = "/api/quotes/"


def detail_url(quote_id) -> str:
    return f"{QUOTES_URL}{quote_id}/"


def sync_url(quote_id) -> str:
    return f"{QUOTES_URL}{quote_id}/plan-sync/"


@pytest.fixture
def obra(user):
    """Un cliente, dos servicios y un plano de la cuenta."""
    return {
        "client": ClientFactory(owner=user, name="Constructora Reyes"),
        "muro": TariffFactory(owner=user, name="Muro de block", unit_price="350"),
        "limpieza": TariffFactory(
            owner=user, name="Limpieza final", unit_type="unit", unit_price="1500"
        ),
        "plan": Plan.objects.create(owner=user, name="Casa Pérez", document={}),
    }


def plan_line(tariff, quantity: str, **rooms: str) -> dict:
    """Una partida medida por el plano, con lo que cae en cada habitación."""
    line = {"tariff": str(tariff.id), "quantity": quantity, "from_plan": True}
    if rooms:
        line["rooms"] = [
            {"name": name.replace("_", " "), "quantity": qty}
            for name, qty in rooms.items()
        ]
    return line


def rooms_of(item: dict) -> list[tuple[str, Decimal]]:
    return [(room["name"], Decimal(room["quantity"])) for room in item["rooms"]]


def create(authenticated_client, obra, *items: dict):
    return authenticated_client.post(
        QUOTES_URL,
        {
            "client": str(obra["client"].id),
            "plan": str(obra["plan"].id),
            "items": list(items),
        },
        format="json",
    )


@pytest.mark.django_db
class TestEachPlanLineKeepsItsRooms:
    """Nueva iteracion-25 - Un mismo concepto en varias habitaciones."""

    def test_a_line_measured_in_two_rooms_keeps_both_quantities(
        self, authenticated_client, obra
    ) -> None:
        response = create(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "20.00", Cuarto_A="12.00", Cuarto_B="8.00"),
        )

        assert response.status_code == status.HTTP_201_CREATED
        [line] = response.data["items"]
        # El resumen global no cambia: una partida con la cantidad de todo el plano.
        assert Decimal(line["quantity"]) == Decimal("20.00")
        assert Decimal(line["subtotal"]) == Decimal("7000.00")
        assert Decimal(response.data["total"]) == Decimal("7000.00")
        assert rooms_of(line) == [
            ("Cuarto A", Decimal("12.00")),
            ("Cuarto B", Decimal("8.00")),
        ]

    def test_the_rooms_come_back_with_only_their_name_and_quantity(
        self, authenticated_client, obra
    ) -> None:
        """VAL-05 · US-12 — el importe de una habitación lo calcula el documento."""
        line = plan_line(obra["muro"], "20.00", Cuarto_A="12.00")
        line["rooms"][0]["subtotal"] = "1.00"

        response = create(authenticated_client, obra, line)

        assert response.data["items"][0]["rooms"] == [
            {"name": "Cuarto A", "quantity": "12.00"}
        ]

    def test_a_line_added_by_hand_has_no_rooms(
        self, authenticated_client, obra
    ) -> None:
        """Nueva iteracion-25 - Lo agregado a mano va sin habitación."""
        response = create(
            authenticated_client,
            obra,
            {"tariff": str(obra["limpieza"].id), "quantity": "1"},
        )

        assert response.data["items"][0]["rooms"] == []

    def test_the_detail_carries_the_rooms(self, authenticated_client, obra) -> None:
        created = create(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "20.00", Cuarto_A="12.00", Cuarto_B="8.00"),
        ).data

        response = authenticated_client.get(detail_url(created["id"]))

        assert rooms_of(response.data["items"][0]) == [
            ("Cuarto A", Decimal("12.00")),
            ("Cuarto B", Decimal("8.00")),
        ]

    def test_listing_quotes_does_not_ask_once_per_room(
        self, authenticated_client, obra
    ) -> None:
        """Las habitaciones llegan con sus partidas, no una consulta por cada una."""
        create(authenticated_client, obra, plan_line(obra["muro"], "5", Cuarto_A="5"))
        with CaptureQueriesContext(connection) as one:
            authenticated_client.get(QUOTES_URL)
        for _ in range(3):
            create(
                authenticated_client,
                obra,
                plan_line(obra["muro"], "5", Cuarto_A="2", Cuarto_B="3"),
                plan_line(obra["limpieza"], "2", Cuarto_C="1"),
            )

        with CaptureQueriesContext(connection) as four:
            response = authenticated_client.get(QUOTES_URL)

        assert response.data["count"] == 4
        assert len(four.captured_queries) == len(one.captured_queries)


@pytest.mark.django_db
class TestABreakdownThatDoesNotAddUpIsRejected:
    """Caso de borde iteracion-25 - Un reparto que no cuadra."""

    def _rejected(self, authenticated_client, obra, line: dict):
        response = create(authenticated_client, obra, line)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Quote.objects.count() == 0
        assert QuoteItemRoom.objects.count() == 0
        return response.data["items"][0]["rooms"]

    def test_rooms_adding_up_to_more_than_the_line(
        self, authenticated_client, obra
    ) -> None:
        errors = self._rejected(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "10.00", Cuarto_A="6.00", Cuarto_B="4.01"),
        )

        assert errors == [
            "Lo repartido entre las habitaciones no puede pasar de la cantidad de "
            "la partida"
        ]

    def test_less_than_the_line_is_fine_the_rest_has_no_room(
        self, authenticated_client, obra
    ) -> None:
        response = create(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "10.00", Cuarto_A="6.00"),
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_the_same_room_twice_in_a_line(self, authenticated_client, obra) -> None:
        line = plan_line(obra["muro"], "10.00", Cuarto_A="3.00")
        line["rooms"].append({"name": " Cuarto A ", "quantity": "2.00"})

        errors = self._rejected(authenticated_client, obra, line)

        assert errors == ["Cada habitación va una sola vez en la partida"]

    @pytest.mark.parametrize("quantity", ["0", "-1.00", "1.005", "abc"])
    def test_a_room_quantity_that_is_not_a_positive_figure(
        self, authenticated_client, obra, quantity
    ) -> None:
        """VAL-05 · US-12"""
        errors = self._rejected(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "10.00", Cuarto_A=quantity),
        )

        assert "quantity" in errors[0]

    def test_a_room_without_a_name(self, authenticated_client, obra) -> None:
        errors = self._rejected(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "10.00", **{"   ": "1.00"}),
        )

        assert errors[0]["name"] == ["Escribe el nombre de la habitación"]

    def test_a_room_name_at_its_limit_is_kept(self, authenticated_client, obra) -> None:
        """VAL-01 · VAL-06 · US-12"""
        name = "H" * ROOM_NAME_MAX_LENGTH

        response = create(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "10.00", **{name: "1.00"}),
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["items"][0]["rooms"][0]["name"] == name

    def test_a_room_name_over_its_limit(self, authenticated_client, obra) -> None:
        """VAL-01 · VAL-06 · US-12"""
        errors = self._rejected(
            authenticated_client,
            obra,
            plan_line(
                obra["muro"], "10.00", **{"H" * (ROOM_NAME_MAX_LENGTH + 1): "1.00"}
            ),
        )

        assert errors[0]["name"] == [
            f"El nombre de la habitación no puede pasar de {ROOM_NAME_MAX_LENGTH} "
            "caracteres"
        ]

    def test_more_rooms_than_a_line_admits(self, authenticated_client, obra) -> None:
        """VAL-06 · US-12 — una lista sobre su máximo"""
        line = plan_line(obra["muro"], "1000.00")
        line["rooms"] = [
            {"name": f"Cuarto {n}", "quantity": "1.00"}
            for n in range(MAX_ROOMS_PER_ITEM + 1)
        ]

        response = create(authenticated_client, obra, line)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "rooms" in response.data["items"][0]
        assert Quote.objects.count() == 0


@pytest.mark.django_db
class TestRequotingUpdatesTheBreakdown:
    """Nueva iteracion-25 - Recotizar actualiza el desglose (US-95)."""

    def _linked(self, authenticated_client, obra) -> dict:
        return create(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "20.00", Cuarto_A="12.00", Cuarto_B="8.00"),
            {"tariff": str(obra["limpieza"].id), "quantity": "1"},
        ).data

    def _sync(self, authenticated_client, obra, quote_id, *items: dict):
        return authenticated_client.post(
            sync_url(quote_id),
            {"plan": str(obra["plan"].id), "items": list(items)},
            format="json",
        )

    def test_the_plan_lines_take_the_new_rooms(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        response = self._sync(
            authenticated_client,
            obra,
            quote["id"],
            plan_line(obra["muro"], "25.00", Cuarto_A="15.00", Estudio="10.00"),
        )

        assert response.status_code == status.HTTP_200_OK
        lines = {item["name"]: item for item in response.data["items"]}
        assert Decimal(lines["Muro de block"]["quantity"]) == Decimal("25.00")
        assert rooms_of(lines["Muro de block"]) == [
            ("Cuarto A", Decimal("15.00")),
            ("Estudio", Decimal("10.00")),
        ]
        # Lo agregado a mano sigue sin habitación.
        assert lines["Limpieza final"]["rooms"] == []

    def test_a_plan_without_rooms_now_leaves_the_line_without_them(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        response = self._sync(
            authenticated_client, obra, quote["id"], plan_line(obra["muro"], "20.00")
        )

        lines = {item["name"]: item for item in response.data["items"]}
        assert lines["Muro de block"]["rooms"] == []
        assert QuoteItemRoom.objects.count() == 0

    def test_a_new_service_enters_with_its_rooms(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)
        piso = TariffFactory(owner=obra["client"].owner, name="Piso", unit_price="400")

        response = self._sync(
            authenticated_client,
            obra,
            quote["id"],
            plan_line(obra["muro"], "20.00", Cuarto_A="12.00", Cuarto_B="8.00"),
            plan_line(piso, "9.00", Cuarto_B="9.00"),
        )

        lines = {item["name"]: item for item in response.data["items"]}
        assert rooms_of(lines["Piso"]) == [("Cuarto B", Decimal("9.00"))]

    def test_a_line_that_leaves_the_plan_takes_its_rooms_with_it(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        self._sync(authenticated_client, obra, quote["id"])

        assert QuoteItemRoom.objects.count() == 0

    def test_a_breakdown_that_does_not_add_up_changes_nothing(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        response = self._sync(
            authenticated_client,
            obra,
            quote["id"],
            plan_line(obra["muro"], "5.00", Cuarto_A="6.00"),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        line = Quote.objects.get(pk=quote["id"]).items.get(tariff=obra["muro"])
        assert line.quantity == Decimal("20.00")
        assert sorted(line.rooms.values_list("name", flat=True)) == [
            "Cuarto A",
            "Cuarto B",
        ]


@pytest.mark.django_db
class TestEditingByHandDoesNotInventRooms:
    """Nueva iteracion-25 - Corregir a mano no inventa habitaciones."""

    def _linked(self, authenticated_client, obra) -> dict:
        return create(
            authenticated_client,
            obra,
            plan_line(obra["muro"], "20.00", Cuarto_A="12.00", Cuarto_B="8.00"),
        ).data

    def _edit(self, authenticated_client, obra, quote_id, *items: dict, **extra):
        # La pantalla de la cotización no sabe de habitaciones: manda sus partidas.
        return authenticated_client.patch(
            detail_url(quote_id),
            {"client": str(obra["client"].id), "items": list(items), **extra},
            format="json",
        )

    def test_editing_something_else_keeps_the_breakdown(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        response = self._edit(
            authenticated_client,
            obra,
            quote["id"],
            {"tariff": str(obra["muro"].id), "quantity": "20.00"},
            {"tariff": str(obra["limpieza"].id), "quantity": "1"},
            notes="Incluye material.",
        )

        assert response.status_code == status.HTTP_200_OK
        lines = {item["name"]: item for item in response.data["items"]}
        assert rooms_of(lines["Muro de block"]) == [
            ("Cuarto A", Decimal("12.00")),
            ("Cuarto B", Decimal("8.00")),
        ]
        assert lines["Limpieza final"]["rooms"] == []

    def test_raising_the_quantity_keeps_the_rooms_and_the_rest_has_none(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        response = self._edit(
            authenticated_client,
            obra,
            quote["id"],
            {"tariff": str(obra["muro"].id), "quantity": "23.00"},
        )

        [line] = response.data["items"]
        assert Decimal(line["quantity"]) == Decimal("23.00")
        assert rooms_of(line) == [
            ("Cuarto A", Decimal("12.00")),
            ("Cuarto B", Decimal("8.00")),
        ]

    def test_lowering_the_quantity_leaves_the_line_without_rooms(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        response = self._edit(
            authenticated_client,
            obra,
            quote["id"],
            {"tariff": str(obra["muro"].id), "quantity": "15.00"},
        )

        [line] = response.data["items"]
        assert Decimal(line["quantity"]) == Decimal("15.00")
        assert line["rooms"] == []

    def test_a_breakdown_sent_with_the_edit_replaces_the_old_one(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked(authenticated_client, obra)

        response = self._edit(
            authenticated_client,
            obra,
            quote["id"],
            plan_line(obra["muro"], "20.00", Cuarto_B="20.00"),
        )

        assert rooms_of(response.data["items"][0]) == [("Cuarto B", Decimal("20.00"))]
