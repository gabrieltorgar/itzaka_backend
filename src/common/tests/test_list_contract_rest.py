"""TEC Contrato de listas: las listas que no son una pantalla (iteracion-17 #1).

Los pagos de un proyecto, sus avances, el reparto, los pagos al personal y los
archivos y el mobiliario del editor no tienen tabla propia, pero son listas del
API: llegan por páginas, con sus filtros declarados y un orden estable. Los
parámetros que ya publicaban (``?project=``, ``?worker=``) siguen sirviendo.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.assets.models import CatalogModel, PlanAsset
from apps.payments.models import Payment
from apps.projects.models import Progress
from apps.staff.models import Assignment, WorkerPayment
from apps.staff.tests.factories import WorkerFactory
from apps.staff.tests.test_staff import make_project


def ids(response) -> list[str]:
    return [row["id"] for row in response.data["results"]]


@pytest.mark.django_db
class TestLosPagosDeUnProyecto:
    def test_por_paginas_y_por_proyecto(self, user, authenticated_client) -> None:
        project, _, _, _ = make_project(user)
        otro, _, _, _ = make_project(user)
        del_proyecto = Payment.objects.create(
            owner=user, project=project, amount=Decimal("100"), date=date(2026, 10, 2)
        )
        Payment.objects.create(
            owner=user, project=otro, amount=Decimal("50"), date=date(2026, 10, 1)
        )

        response = authenticated_client.get(
            "/api/payments/", {"project": str(project.id)}
        )

        assert response.data["count"] == 1
        assert ids(response) == [str(del_proyecto.id)]

    def test_un_proyecto_que_no_es_un_id_es_400(self, authenticated_client) -> None:
        response = authenticated_client.get(
            "/api/payments/", {"project": "no-es-un-id"}
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestLosAvances:
    def test_por_proyecto_y_en_orden_de_fecha(self, user, authenticated_client) -> None:
        project, muro, _, _ = make_project(user)
        otro, otro_muro, _, _ = make_project(user)
        despues = Progress.objects.create(
            project=project,
            quote_item=muro,
            date=date(2026, 10, 5),
            quantity=Decimal("1"),
        )
        antes = Progress.objects.create(
            project=project,
            quote_item=muro,
            date=date(2026, 10, 1),
            quantity=Decimal("1"),
        )
        Progress.objects.create(
            project=otro,
            quote_item=otro_muro,
            date=date(2026, 10, 3),
            quantity=Decimal("1"),
        )

        response = authenticated_client.get(
            "/api/progresses/", {"project": str(project.id)}
        )

        assert ids(response) == [str(antes.id), str(despues.id)]


@pytest.mark.django_db
class TestElRepartoYLosPagosAlPersonal:
    def test_el_reparto_de_un_proyecto(self, user, authenticated_client) -> None:
        project, muro, _, _ = make_project(user)
        otro, otro_muro, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan")
        aqui = Assignment.objects.create(
            project=project,
            quote_item=muro,
            worker=juan,
            quantity=Decimal("10"),
            unit_price=Decimal("50"),
        )
        Assignment.objects.create(
            project=otro,
            quote_item=otro_muro,
            worker=juan,
            quantity=Decimal("5"),
            unit_price=Decimal("50"),
        )

        response = authenticated_client.get(
            "/api/assignments/", {"project": str(project.id)}
        )

        assert ids(response) == [str(aqui.id)]

    def test_los_pagos_de_una_persona(self, user, authenticated_client) -> None:
        juan = WorkerFactory(owner=user, name="Juan")
        luis = WorkerFactory(owner=user, name="Luis")
        a_juan = WorkerPayment.objects.create(
            owner=user, worker=juan, amount=Decimal("100"), date=date(2026, 10, 1)
        )
        WorkerPayment.objects.create(
            owner=user, worker=luis, amount=Decimal("100"), date=date(2026, 10, 1)
        )

        response = authenticated_client.get(
            "/api/worker-payments/", {"worker": str(juan.id)}
        )

        assert response.data["count"] == 1
        assert ids(response) == [str(a_juan.id)]


@pytest.mark.django_db
class TestLosArchivosYElMobiliarioDelEditor:
    def test_los_archivos_llegan_por_paginas(self, user, authenticated_client) -> None:
        for n in range(3):
            PlanAsset.objects.create(
                owner=user, kind="texture", path=f"textures/{n}.jpg", file="x.jpg"
            )

        response = authenticated_client.get("/api/plan-assets/", {"page_size": 2})

        assert response.data["count"] == 3
        assert [row["path"] for row in response.data["results"]] == [
            "textures/0.jpg",
            "textures/1.jpg",
        ]
        assert response.data["next"] is not None

    def test_el_mobiliario_llega_por_paginas(self, user, authenticated_client) -> None:
        for n in range(3):
            CatalogModel.objects.create(
                owner=user,
                model_id=f"lib#{n}",
                fiche={"id": f"lib#{n}", "name": str(n)},
            )

        primera = authenticated_client.get("/api/plan-models/", {"page_size": 2})
        segunda = authenticated_client.get(
            "/api/plan-models/", {"page_size": 2, "page": 2}
        )

        assert primera.data["count"] == 3
        assert [fiche["id"] for fiche in primera.data["results"]] == ["lib#0", "lib#1"]
        assert [fiche["id"] for fiche in segunda.data["results"]] == ["lib#2"]
        assert segunda.data["next"] is None
