"""US-96 · US-97: la lista del personal del servidor (iteracion-17 #8).

Fuente: backlog 4.9 → US-96 list_spec y los cambios «iteracion-17» de US-96 y
US-97.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.catalog.tests.factories import TariffFactory
from apps.projects.models import Progress
from apps.staff.models import Assignment, Worker, WorkerPayment, WorkerService
from apps.staff.tests.factories import WorkerFactory
from apps.staff.tests.test_staff import make_project

URL = "/api/workers/"


def nombres(response) -> list[str]:
    return [row["name"] for row in response.data["results"]]


def deberle(user, project, item, worker, *, ganado: str, pagado: str = "0") -> None:
    """Que ``worker`` haya ganado ``ganado`` en obra y se le hayan pagado ``pagado``."""
    Progress.objects.create(
        project=project,
        quote_item=item,
        date=date(2026, 10, 1),
        quantity=Decimal("1"),
        worker=worker,
        labor_unit_price=Decimal(ganado),
    )
    if Decimal(pagado) > 0:
        WorkerPayment.objects.create(
            owner=user, worker=worker, amount=Decimal(pagado), date=date(2026, 10, 2)
        )


@pytest.mark.django_db
class TestLaListaDelPersonal:
    def test_primero_a_quienes_mas_se_les_debe(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - El servidor entrega una página."""
        project, item, _, _ = make_project(user)
        poco = WorkerFactory(owner=user, name="Poco")
        mucho = WorkerFactory(owner=user, name="Mucho")
        WorkerFactory(owner=user, name="Nada")
        deberle(user, project, item, poco, ganado="500", pagado="200")
        deberle(user, project, item, mucho, ganado="9000")

        response = authenticated_client.get(URL)

        assert response.data["count"] == 3
        assert nombres(response) == ["Mucho", "Poco", "Nada"]
        assert Decimal(response.data["results"][0]["balance"]) == Decimal("9000.00")

    def test_buscar_tambien_por_servicio(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Buscar también por servicio."""
        plomeria = TariffFactory(owner=user, name="Plomería general")
        pintura = TariffFactory(owner=user, name="Pintura")
        plomero = WorkerFactory(owner=user, name="Juan Pérez")
        WorkerService.objects.create(worker=plomero, tariff=plomeria)
        WorkerService.objects.create(worker=plomero, tariff=pintura)
        WorkerFactory(owner=user, name="Plomos y más")
        WorkerFactory(owner=user, name="Otro")

        response = authenticated_client.get(URL, {"search": "plom"})

        assert sorted(nombres(response)) == ["Juan Pérez", "Plomos y más"]

    def test_con_saldo_en_toda_la_cuenta(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Con saldo en toda la cuenta."""
        project, item, _, _ = make_project(user)
        debe = WorkerFactory(owner=user, name="Se le debe")
        pagado = WorkerFactory(owner=user, name="Ya se le pagó")
        WorkerFactory(owner=user, name="Sin trabajo")
        deberle(user, project, item, debe, ganado="300")
        deberle(user, project, item, pagado, ganado="300", pagado="300")

        con = authenticated_client.get(URL, {"has_balance": "true"})
        sin = authenticated_client.get(URL, {"has_balance": "false"})

        assert nombres(con) == ["Se le debe"]
        assert sorted(nombres(sin)) == ["Sin trabajo", "Ya se le pagó"]

    def test_un_anticipo_no_es_saldo(self, user, authenticated_client) -> None:
        project, item, _, _ = make_project(user)
        adelantado = WorkerFactory(owner=user, name="Adelantado")
        deberle(user, project, item, adelantado, ganado="100", pagado="400")

        response = authenticated_client.get(URL, {"has_balance": "true"})

        assert nombres(response) == []

    def test_por_tipo_y_por_nombre(self, user, authenticated_client) -> None:
        WorkerFactory(owner=user, name="Zapata")
        WorkerFactory(owner=user, name="Álvarez")
        WorkerFactory(owner=user, name="Muñoz Hermanos", kind=Worker.Kind.COMPANY)

        empresas = authenticated_client.get(URL, {"kind": "company"})
        por_nombre = authenticated_client.get(URL, {"ordering": "name"})

        assert nombres(empresas) == ["Muñoz Hermanos"]
        assert nombres(por_nombre) == ["Álvarez", "Muñoz Hermanos", "Zapata"]

    def test_quienes_hacen_un_servicio(self, user, authenticated_client) -> None:
        """US-97: al repartir, primero quienes hacen el servicio de la partida."""
        muro = TariffFactory(owner=user, name="Muro de block")
        hace = WorkerFactory(owner=user, name="Lo hace")
        WorkerService.objects.create(worker=hace, tariff=muro)
        WorkerFactory(owner=user, name="No lo hace")

        response = authenticated_client.get(URL, {"service": str(muro.id)})

        assert nombres(response) == ["Lo hace"]

    def test_buscar_a_quien_hace_el_trabajo(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Buscar a quien hace el trabajo (US-97)."""
        WorkerFactory(owner=user, name="Juan Pérez")
        WorkerFactory(
            owner=user, name="Construcciones Juanes", kind=Worker.Kind.COMPANY
        )
        WorkerFactory(owner=user, name="Pedro Ruiz")

        response = authenticated_client.get(URL, {"search": "juan"})

        assert sorted(nombres(response)) == ["Construcciones Juanes", "Juan Pérez"]

    def test_el_de_otra_cuenta_no_aparece(
        self, user, authenticated_client, user_factory
    ) -> None:
        WorkerFactory(owner=user_factory(), name="Ajeno")

        assert authenticated_client.get(URL).data["count"] == 0


@pytest.mark.django_db
class TestLosTotalesDeTodaLaCuenta:
    """Los totales de arriba de la lista suman a todos, no solo a la página."""

    def test_lo_que_se_debe_y_lo_repartido(self, user, authenticated_client) -> None:
        project, item, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan")
        luis = WorkerFactory(owner=user, name="Luis")
        deberle(user, project, item, juan, ganado="500", pagado="200")
        deberle(user, project, item, luis, ganado="9000")
        Assignment.objects.create(
            project=project,
            quote_item=item,
            worker=juan,
            quantity=Decimal("10"),
            unit_price=Decimal("50"),
        )

        response = authenticated_client.get(f"{URL}totals/")

        assert response.data == {"balance": "9300.00", "committed_value": "500.00"}

    def test_sin_sesion_es_401(self, api_client) -> None:
        assert api_client.get(f"{URL}totals/").status_code == 401
