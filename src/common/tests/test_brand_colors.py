"""La marca es Itzaka (iteracion-20 · US-127): logo y colores.

Los correos de la casa salen en blanco con el logo a color, el admin usa la
paleta de piedra y una cuenta nueva pinta sus documentos en obsidiana. Las
cuentas que ya existen conservan el color que tienen guardado.
"""

import pytest

from apps.accounts.models import DEFAULT_ORGANIZATION_COLOR, Organization
from common.brand import GROUP_SIGNATURE
from common.branding import BRAND_LOGO_PATH, house_brand
from common.emails import render_email
from core.settings_unfold import UNFOLD

OBSIDIANA = "#141517"


class TestElAdmin:
    def test_the_admin_wears_the_stone_palette(self) -> None:
        """US-127 - El admin usa la obsidiana y los neutrales de piedra."""
        assert UNFOLD["COLORS"]["primary"]["800"] == OBSIDIANA
        assert UNFOLD["COLORS"]["base"]["950"] == OBSIDIANA
        assert set(UNFOLD["COLORS"]["primary"]) == set(UNFOLD["COLORS"]["base"])


class TestElCorreoDeLaCasa:
    def test_the_house_email_is_white_with_the_color_logo(self) -> None:
        """US-127 - Sin membrete, encabezado blanco con el logo a color (PNG @2x)."""
        marca = house_brand()

        assert marca.color == OBSIDIANA
        assert BRAND_LOGO_PATH == "/email-logo@2x.png"
        assert marca.logo_url.endswith("/email-logo@2x.png")

        html = render_email(brand=marca, title="Hola", intro="Texto")
        assert "background:#FFFFFF;padding:20px 24px" in html
        assert f"color:{OBSIDIANA};font-size:18px" in html
        assert GROUP_SIGNATURE in html

    def test_the_email_uses_the_stone_neutrals(self) -> None:
        """US-127 - Grises de piedra y pie legible (AA), sin grises azulados."""
        html = render_email(
            brand=house_brand(), title="Hola", intro="Texto", note="Nota"
        )

        for viejo in ("#0F172A", "#334155", "#64748B", "#475569", "#94A3B8", "#F1F5F9"):
            assert viejo not in html
        assert "#5E5A55" in html


@pytest.mark.django_db
class TestElColorPorDefecto:
    def test_a_new_organization_starts_in_obsidian(self, user_factory) -> None:
        """US-127 - Una cuenta nueva sin color propio pinta en obsidiana."""
        assert DEFAULT_ORGANIZATION_COLOR == OBSIDIANA
        assert Organization._meta.get_field("color").default == OBSIDIANA

    def test_an_existing_color_is_kept(self, user_factory) -> None:
        """Caso de borde - El color que una cuenta ya tiene guardado no cambia."""
        cuenta = user_factory()
        organizacion = Organization.objects.create(user=cuenta, color="#1E56D6")

        organizacion.refresh_from_db()
        assert organizacion.color == "#1E56D6"
