"""Lo que hacían las vistas del personal, en sus capas (iteracion-13 #4, MAN-01)."""

from decimal import Decimal

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.staff.selectors import get_owned_worker
from apps.staff.services import ensure_single_self, hand_out
from apps.staff.tests.factories import WorkerFactory
from common.tests.test_cross_account import cuenta_completa


@pytest.mark.django_db
class TestSelectoresDelPersonal:
    def test_a_worker_is_found_only_in_its_account(self, user) -> None:
        mio = WorkerFactory(owner=user)
        ajeno = WorkerFactory()

        assert get_owned_worker(owner=user, worker_id=mio.id) == mio
        assert get_owned_worker(owner=user, worker_id=ajeno.id) is None
        assert get_owned_worker(owner=user, worker_id=None) is None


@pytest.mark.django_db
class TestServiciosDelPersonal:
    def test_there_is_only_one_self(self, user) -> None:
        yo = WorkerFactory(owner=user, is_self=True)

        with pytest.raises(ValidationError):
            ensure_single_self(owner=user)
        ensure_single_self(owner=user, exclude=yo.pk)
        ensure_single_self(owner=UserFactory())

    def test_handing_out_a_foreign_project_is_not_found(self, user) -> None:
        ajena = cuenta_completa(UserFactory())

        with pytest.raises(NotFound):
            hand_out(
                owner=user,
                project=ajena["project"],
                quote_item=ajena["quote_item"],
                worker=ajena["worker"],
                quantity=Decimal("1"),
            )
