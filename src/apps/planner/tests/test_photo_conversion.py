"""RED tests for US-129 — convertir la foto de un plano en un plano editable.

Un plano en papel sólo se podía calcar a mano (US-41). La foto viaja al
servidor, una IA con visión lee sus muros y habitaciones, y vuelven en
coordenadas relativas a la foto (0 a 1) para que el editor las ponga sobre ella.
La IA nunca se llama de verdad aquí: cuesta dinero y necesita red.
"""

import base64
import io
import json
from datetime import timedelta
from types import SimpleNamespace

import anthropic
import pytest
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework import status

from apps.planner import photo_conversion
from apps.planner.models import PhotoConversion
from apps.planner.photo_conversion import ConversionUnavailable

URL = "/api/plans/photo-conversions/"

UNAVAILABLE = "No pudimos convertir la foto ahora. Inténtalo de nuevo en unos minutos."


def photo_bytes(width: int = 800, height: int = 600, fmt: str = "PNG", **save) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format=fmt, **save)
    return buffer.getvalue()


def upload(content: bytes | None = None, name: str = "plano.png", kind="image/png"):
    return SimpleUploadedFile(name, content or photo_bytes(), content_type=kind)


def plan_reading(width: int, height: int) -> dict:
    """Lo que la IA devuelve para una casa de dos cuartos, en píxeles."""
    return {
        "is_floor_plan": True,
        "image_width": width,
        "image_height": height,
        "walls": [
            {"x1": 0, "y1": 0, "x2": width, "y2": 0},
            {"x1": width, "y1": 0, "x2": width, "y2": height},
            {"x1": width / 2, "y1": 0, "x2": width / 2, "y2": height},
        ],
        "rooms": [
            {
                "name": "Cocina",
                "points": [
                    {"x": 0, "y": 0},
                    {"x": width / 2, "y": 0},
                    {"x": width / 2, "y": height},
                    {"x": 0, "y": height},
                ],
            },
            {
                "name": "",
                "points": [
                    {"x": width / 2, "y": 0},
                    {"x": width, "y": 0},
                    {"x": width, "y": height},
                ],
            },
        ],
    }


@pytest.fixture
def reads_a_house(mocker):
    """La IA lee una casa en la foto que recibe, con su tamaño."""

    def fake(image: bytes, media_type: str, measures=None) -> dict:
        width, height = Image.open(io.BytesIO(image)).size
        return plan_reading(width, height)

    return mocker.patch.object(photo_conversion, "read_plan", side_effect=fake)


def cotas_reading(width: int, height: int, *cotas) -> dict:
    """Lo que la lectura rápida encuentra: sólo las cotas, en píxeles."""
    return {
        "is_floor_plan": True,
        "image_width": width,
        "image_height": height,
        "dimensions": [
            {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "metres": metres}
            for x1, y1, x2, y2, metres in cotas
        ],
    }


def sees(mocker, *cotas):
    """La lectura rápida de las cotas encuentra éstas, en la foto que recibe."""

    def fake(image: bytes, media_type: str) -> dict:
        width, height = Image.open(io.BytesIO(image)).size
        return cotas_reading(width, height, *cotas)

    return mocker.patch.object(photo_conversion, "read_cotas", side_effect=fake)


@pytest.fixture(autouse=True)
def legible_cotas(request, mocker):
    """Por omisión el plano trae su ancho y su alto escritos y legibles."""
    if "no_cotas_mock" in request.keywords:
        return None
    return sees(mocker, (0, 10, 1568, 10, 15.68), (10, 0, 10, 1176, 11.76))


@pytest.mark.django_db
class TestPhotoConversionEndpoint:
    """US-129: de la foto de un plano en papel a muros y habitaciones."""

    def test_the_photo_comes_back_as_walls(self, authenticated_client, reads_a_house):
        """Flujo principal - Subir la foto y obtener los muros."""
        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        walls = response.data["walls"]
        assert len(walls) == 3
        # Relativo a la foto: el primer muro recorre todo el borde de arriba.
        assert walls[0] == {"start": {"x": 0.0, "y": 0.0}, "end": {"x": 1.0, "y": 0.0}}
        assert walls[2]["start"] == {"x": 0.5, "y": 0.0}
        # Sin puertas ni ventanas leídas, la lista viene vacía, no ausente.
        assert response.data["openings"] == []

    def test_the_polished_photo_comes_back_for_the_background(
        self, authenticated_client, reads_a_house
    ):
        """Flujo principal - La foto pulida queda de fondo, con su tamaño."""
        response = authenticated_client.post(
            URL, {"photo": upload(photo_bytes(800, 600))}, format="multipart"
        )

        image = response.data["image"]
        assert image["src"].startswith("data:image/png;base64,")
        assert (image["width"], image["height"]) == (1568, 1176)
        # Es la misma imagen que leyó la IA: los muros caen exactos sobre ella.
        sent = reads_a_house.call_args.args[0]
        assert image["src"].endswith(base64.b64encode(sent).decode())

    def test_closed_spaces_come_back_as_rooms(
        self, authenticated_client, reads_a_house
    ):
        """Flujo principal - Las habitaciones salen con su nombre si lo trae."""
        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        rooms = response.data["rooms"]
        assert [room["name"] for room in rooms] == ["Cocina", None]
        assert rooms[0]["points"][2] == {"x": 0.5, "y": 1.0}
        assert len(rooms[1]["points"]) == 3

    def test_each_conversion_counts_for_the_day(
        self, authenticated_client, reads_a_house, user
    ):
        """Caso de borde - Tope diario: cada foto convertida resta una del día."""
        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.data["remaining_today"] == 4
        conversion = PhotoConversion.objects.get(owner=user)
        assert (conversion.walls, conversion.rooms) == (3, 2)

    def test_a_photo_that_is_not_a_plan_brings_no_walls(
        self, authenticated_client, mocker
    ):
        """Caso alternativo - La foto no parece un plano."""
        mocker.patch.object(
            photo_conversion,
            "read_plan",
            return_value={
                "is_floor_plan": False,
                "image_width": 800,
                "image_height": 600,
                "walls": [{"x1": 1, "y1": 1, "x2": 50, "y2": 50}],
                "rooms": [],
            },
        )

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["walls"] == []
        assert response.data["rooms"] == []

    def test_a_file_that_is_not_an_image_is_refused(
        self, authenticated_client, reads_a_house
    ):
        """Caso alternativo - Archivo no admitido."""
        response = authenticated_client.post(
            URL,
            {"photo": upload(b"no soy una foto", "plano.txt", "text/plain")},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Formato de imagen no admitido" in str(response.data["photo"])
        reads_a_house.assert_not_called()

    def test_a_gif_is_refused(self, authenticated_client, reads_a_house):
        """Caso alternativo - Sólo PNG, JPG y WEBP."""
        response = authenticated_client.post(
            URL,
            {"photo": upload(photo_bytes(fmt="GIF"), "plano.gif", "image/gif")},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Formato de imagen no admitido" in str(response.data["photo"])

    def test_a_heavy_photo_is_refused(
        self, authenticated_client, reads_a_house, settings
    ):
        """Caso alternativo - La foto pesa demasiado para enviarla."""
        settings.PHOTO_PLAN_MAX_BYTES = 1024 * 1024
        heavy = photo_bytes() + b"\0" * (1024 * 1024)

        response = authenticated_client.post(
            URL, {"photo": upload(heavy)}, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "La foto pesa más de 1 MB" in str(response.data["photo"])
        reads_a_house.assert_not_called()

    def test_a_missing_photo_is_asked_for(self, authenticated_client, reads_a_house):
        """Caso alternativo - Sin foto no hay nada que convertir."""
        response = authenticated_client.post(URL, {}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Sube la foto del plano" in str(response.data["photo"])

    def test_the_sixth_photo_of_the_day_is_refused(
        self, authenticated_client, reads_a_house, user
    ):
        """Caso de borde - Tope diario por cuenta (5 fotos)."""
        for _ in range(5):
            PhotoConversion.objects.create(owner=user, walls=1, rooms=0)

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.data["detail"] == (
            "Llegaste al límite de 5 fotos por día. Vuelve a intentarlo mañana."
        )
        reads_a_house.assert_not_called()

    def test_yesterday_does_not_count(self, authenticated_client, reads_a_house, user):
        """Caso de borde - El tope vuelve a empezar cada día."""
        for _ in range(5):
            old = PhotoConversion.objects.create(owner=user, walls=1, rooms=0)
            PhotoConversion.objects.filter(pk=old.pk).update(
                created_at=timezone.now() - timedelta(days=1)
            )

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK

    def test_other_accounts_do_not_count(
        self, authenticated_client, reads_a_house, user_factory
    ):
        """Caso de borde - El tope es de cada cuenta."""
        other = user_factory()
        for _ in range(5):
            PhotoConversion.objects.create(owner=other, walls=1, rooms=0)

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["remaining_today"] == 4

    def test_when_the_service_fails_nothing_changes(
        self, authenticated_client, mocker, user
    ):
        """Caso de borde - El servicio no responde."""
        mocker.patch.object(
            photo_conversion, "read_plan", side_effect=ConversionUnavailable()
        )

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["detail"] == UNAVAILABLE
        # Lo que no se convirtió no se cobra del tope.
        assert not PhotoConversion.objects.filter(owner=user).exists()

    def test_only_with_a_session(self, api_client, reads_a_house):
        """Caso de borde - Sólo con sesión."""
        response = api_client.post(URL, {"photo": upload()}, format="multipart")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        reads_a_house.assert_not_called()

    def test_conversions_are_visible_in_the_admin(self) -> None:
        """Plataforma - todo modelo se ve en el admin."""
        assert admin.site.is_registered(PhotoConversion)


class TestPreparePhoto:
    """La foto que viaja a la IA: derecha, pulida, en blanco y negro y en PNG."""

    def test_the_photo_comes_out_polished_at_the_standard_size(self) -> None:
        prepared, media_type = photo_conversion.prepare_photo(photo_bytes(4000, 3000))

        assert media_type == "image/png"
        image = Image.open(io.BytesIO(prepared))
        assert image.size == (1568, 1176)
        assert image.mode == "L"
        assert set(image.getdata()) <= {0, 255}

    def test_a_small_photo_is_brought_to_the_standard_size(self) -> None:
        prepared, _ = photo_conversion.prepare_photo(photo_bytes(800, 600, "WEBP"))

        assert Image.open(io.BytesIO(prepared)).size == (1568, 1176)

    def test_a_phone_photo_is_turned_upright(self) -> None:
        """El teléfono guarda la foto acostada y dice cómo girarla (EXIF)."""
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: girar 90° a la derecha
        raw = photo_bytes(800, 600, "JPEG", exif=exif.tobytes())

        prepared, _ = photo_conversion.prepare_photo(raw)

        assert Image.open(io.BytesIO(prepared)).size == (1176, 1568)

    def test_a_transparent_png_still_travels(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGBA", (300, 200), (0, 0, 0, 0)).save(buffer, format="PNG")

        prepared, _ = photo_conversion.prepare_photo(buffer.getvalue())

        # Lo transparente cuenta como papel: blanco, no negro.
        assert set(Image.open(io.BytesIO(prepared)).getdata()) == {255}


class TestToPlan:
    """De los píxeles de la IA a coordenadas relativas, sin basura."""

    def test_points_outside_the_photo_are_brought_back(self) -> None:
        result = photo_conversion.to_plan(
            {
                "is_floor_plan": True,
                "image_width": 100,
                "image_height": 50,
                "walls": [{"x1": -10, "y1": 25, "x2": 130, "y2": 25}],
                "rooms": [],
            }
        )

        assert result["walls"] == [
            {"start": {"x": 0.0, "y": 0.5}, "end": {"x": 1.0, "y": 0.5}}
        ]

    def test_walls_without_length_and_rooms_without_area_are_dropped(self) -> None:
        result = photo_conversion.to_plan(
            {
                "is_floor_plan": True,
                "image_width": 100,
                "image_height": 100,
                "walls": [{"x1": 10, "y1": 10, "x2": 10, "y2": 10}],
                "rooms": [
                    {"name": "Baño", "points": [{"x": 1, "y": 1}, {"x": 5, "y": 5}]}
                ],
            }
        )

        assert result == {"walls": [], "rooms": [], "openings": [], "dimensions": []}

    def test_long_names_are_trimmed(self) -> None:
        result = photo_conversion.to_plan(
            {
                "is_floor_plan": True,
                "image_width": 10,
                "image_height": 10,
                "walls": [],
                "rooms": [
                    {
                        "name": "  " + "Sala " * 30,
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 10, "y": 0},
                            {"x": 0, "y": 10},
                        ],
                    }
                ],
            }
        )

        assert len(result["rooms"][0]["name"]) <= 60
        assert result["rooms"][0]["name"].startswith("Sala")


def claude_reply(payload: dict, stop_reason: str = "end_turn"):
    """Una respuesta de la API con el JSON en su bloque de texto."""
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=json.dumps(payload)),
        ],
    )


JPEG = photo_bytes(800, 600, "JPEG")


class TestReadPlan:
    """La llamada a Claude: cómo se pide y qué se hace cuando falla."""

    @pytest.fixture
    def client(self, mocker, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        fake = mocker.Mock()
        mocker.patch.object(photo_conversion.anthropic, "Anthropic", return_value=fake)
        return fake

    def test_the_photo_and_the_shape_of_the_answer_are_sent(self, client) -> None:
        client.beta.messages.create.return_value = claude_reply(plan_reading(800, 600))

        reading = photo_conversion.read_plan(JPEG, "image/jpeg")

        assert reading["walls"][0] == {"x1": 0, "y1": 0, "x2": 800, "y2": 0}
        kwargs = client.beta.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-5-5"
        image = kwargs["messages"][0]["content"][0]
        assert image["type"] == "image"
        assert image["source"]["media_type"] == "image/jpeg"
        schema = kwargs["output_config"]["format"]["schema"]
        assert set(schema["required"]) >= {"is_floor_plan", "walls", "rooms"}
        # Las puertas y ventanas vienen aparte, cada una con su tipo.
        assert "openings" in schema["required"]
        kinds = schema["properties"]["openings"]["items"]["properties"]["kind"]
        assert kinds["enum"] == ["door", "window"]
        # Las cotas, con lo que dicen en metros.
        assert "dimensions" in schema["required"]
        cota = schema["properties"]["dimensions"]["items"]["properties"]
        assert set(cota) == {"x1", "y1", "x2", "y2", "metres"}
        assert kwargs["fallbacks"] == "default"
        # Claude sabe de qué tamaño es la foto, y la respuesta lo trae.
        assert "800 × 600" in kwargs["messages"][0]["content"][1]["text"]
        assert (reading["image_width"], reading["image_height"]) == (800, 600)

    def test_the_wait_is_bounded_to_a_minute(self, client) -> None:
        client.beta.messages.create.return_value = claude_reply(plan_reading(10, 10))

        photo_conversion.read_plan(JPEG, "image/jpeg")

        options = photo_conversion.anthropic.Anthropic.call_args.kwargs
        assert options["timeout"] == 60
        # Un reintento duplicaría la espera del arquitecto: mejor decirle.
        assert options["max_retries"] == 0

    def test_without_a_key_the_service_is_unavailable(self, settings) -> None:
        settings.ANTHROPIC_API_KEY = ""

        with pytest.raises(ConversionUnavailable):
            photo_conversion.read_plan(JPEG, "image/jpeg")

    def test_a_timeout_is_unavailable(self, client) -> None:
        client.beta.messages.create.side_effect = anthropic.APITimeoutError(
            request=mocker_request()
        )

        with pytest.raises(ConversionUnavailable):
            photo_conversion.read_plan(JPEG, "image/jpeg")

    def test_an_api_error_is_unavailable(self, client) -> None:
        client.beta.messages.create.side_effect = anthropic.APIConnectionError(
            request=mocker_request()
        )

        with pytest.raises(ConversionUnavailable):
            photo_conversion.read_plan(JPEG, "image/jpeg")

    def test_a_refusal_is_unavailable(self, client) -> None:
        client.beta.messages.create.return_value = claude_reply({}, "refusal")

        with pytest.raises(ConversionUnavailable):
            photo_conversion.read_plan(JPEG, "image/jpeg")

    def test_a_cut_answer_is_unavailable(self, client) -> None:
        reply = claude_reply(plan_reading(10, 10), "max_tokens")
        reply.content[1].text = reply.content[1].text[:20]
        client.beta.messages.create.return_value = reply

        with pytest.raises(ConversionUnavailable):
            photo_conversion.read_plan(JPEG, "image/jpeg")


def mocker_request():
    """Una petición cualquiera, que es lo que piden los errores del SDK."""
    import httpx2

    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.django_db
class TestMeasuresBeforeReading:
    """Cambio iteracion-7 - Las medidas del plano, antes de que lo lea la IA."""

    def test_a_plan_with_its_width_and_height_written_is_read_at_their_scale(
        self, authenticated_client, reads_a_house, legible_cotas
    ):
        """Cambio iteracion-7 - El plano trae sus medidas."""
        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "needs_measures" not in response.data
        legible_cotas.assert_called_once()
        # 1568 px de la foto pulida son 15,68 m: 1 cm por píxel.
        assert response.data["scale"] == "cotas"
        assert response.data["metres_per_pixel"] == pytest.approx(0.01)
        # La cota se busca en la foto ya pulida, la misma que leerá la IA.
        sent = legible_cotas.call_args.args[0]
        assert sent == reads_a_house.call_args.args[0]

    def test_without_cotas_the_measures_are_asked_before_reading(
        self, authenticated_client, reads_a_house, mocker, user
    ):
        """Cambio iteracion-7 - El plano no trae medidas."""
        sees(mocker)

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["needs_measures"] is True
        assert response.data["missing"] == ["width", "height"]
        # Con la foto pulida, para que el arquitecto sepa de qué lado se habla.
        assert response.data["image"]["src"].startswith("data:image/png;base64,")
        # La IA no lee el plano todavía, y no se gasta una foto del día.
        reads_a_house.assert_not_called()
        assert not PhotoConversion.objects.filter(owner=user).exists()
        assert response.data["remaining_today"] == 5

    def test_only_the_missing_side_is_asked(
        self, authenticated_client, reads_a_house, mocker
    ):
        """Cambio iteracion-7 - Falta un solo lado."""
        # Una cota horizontal legible; la vertical no se pudo leer (0).
        sees(mocker, (0, 10, 784, 10, 7.84), (10, 0, 10, 600, 0))

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.data["missing"] == ["height"]

    def test_with_the_measures_given_the_plan_comes_at_their_scale(
        self, authenticated_client, reads_a_house, legible_cotas, user
    ):
        """Cambio iteracion-7 - Escalado con el ancho y el alto del cuestionario."""
        response = authenticated_client.post(
            URL,
            {"photo": upload(), "width_m": "31.36", "height_m": "23.52"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        # Ya no se buscan las cotas: las medidas las dio el arquitecto.
        legible_cotas.assert_not_called()
        # La IA las recibe para aproximar el resto de los muros.
        assert reads_a_house.call_args.kwargs["measures"] == {
            "width_m": 31.36,
            "height_m": 23.52,
        }
        # Los muros leídos ocupan 1568 × 1176 px: 2 cm por píxel.
        assert response.data["scale"] == "medidas"
        assert response.data["metres_per_pixel"] == pytest.approx(0.02)
        assert PhotoConversion.objects.filter(owner=user).count() == 1

    def test_with_one_side_given_the_other_comes_from_its_cota(
        self, authenticated_client, reads_a_house, mocker
    ):
        """Cambio iteracion-7 - Sólo se dio el lado que faltaba."""
        response = authenticated_client.post(
            URL, {"photo": upload(), "height_m": "23.52"}, format="multipart"
        )

        assert reads_a_house.call_args.kwargs["measures"] == {"height_m": 23.52}
        assert response.data["metres_per_pixel"] == pytest.approx(0.02)

    def test_going_on_without_measures_converts_as_before(
        self, authenticated_client, reads_a_house, legible_cotas
    ):
        """Caso alternativo iteracion-7 - Seguir sin medidas."""
        response = authenticated_client.post(
            URL, {"photo": upload(), "skip_measures": "true"}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        legible_cotas.assert_not_called()
        assert reads_a_house.call_args.kwargs["measures"] is None
        assert response.data["scale"] is None
        assert response.data["metres_per_pixel"] is None
        assert len(response.data["walls"]) == 3

    @pytest.mark.parametrize("value", ["0", "-2", "ocho"])
    def test_a_measure_that_is_not_positive_is_refused(
        self, authenticated_client, reads_a_house, value
    ):
        """Caso alternativo iteracion-7 - Medida inválida."""
        response = authenticated_client.post(
            URL, {"photo": upload(), "width_m": value}, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["width_m"] == ["La medida debe ser mayor que 0"]
        reads_a_house.assert_not_called()

    def test_a_photo_that_is_not_a_plan_asks_nothing(
        self, authenticated_client, reads_a_house, mocker
    ):
        """Caso de borde iteracion-7 - Si no es un plano, no hay cuestionario."""
        mocker.patch.object(
            photo_conversion,
            "read_cotas",
            return_value={**cotas_reading(10, 10), "is_floor_plan": False},
        )

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert "needs_measures" not in response.data
        reads_a_house.assert_called_once()

    def test_when_the_quick_reading_fails_nothing_changes(
        self, authenticated_client, reads_a_house, mocker, user
    ):
        """Caso alternativo iteracion-7 - La lectura de las cotas falla."""
        mocker.patch.object(
            photo_conversion, "read_cotas", side_effect=ConversionUnavailable
        )

        response = authenticated_client.post(
            URL, {"photo": upload()}, format="multipart"
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert not PhotoConversion.objects.filter(owner=user).exists()


@pytest.mark.no_cotas_mock
class TestReadCotas:
    """La lectura rápida: sólo las cotas, con el mismo modelo y poco esfuerzo."""

    @pytest.fixture
    def client(self, mocker, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        fake = mocker.Mock()
        mocker.patch.object(photo_conversion.anthropic, "Anthropic", return_value=fake)
        return fake

    def test_only_the_cotas_are_asked_for(self, client) -> None:
        client.beta.messages.create.return_value = claude_reply(
            {
                "is_floor_plan": True,
                "dimensions": [{"x1": 0, "y1": 5, "x2": 400, "y2": 5, "metres": 4}],
            }
        )

        reading = photo_conversion.read_cotas(JPEG, "image/jpeg")

        assert reading["dimensions"][0]["metres"] == 4
        assert (reading["image_width"], reading["image_height"]) == (800, 600)
        kwargs = client.beta.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-5-5"
        assert kwargs["output_config"]["effort"] == "low"
        schema = kwargs["output_config"]["format"]["schema"]
        assert set(schema["required"]) == {"is_floor_plan", "dimensions"}
        assert kwargs["fallbacks"] == "default"

    def test_a_refusal_is_unavailable(self, client) -> None:
        client.beta.messages.create.return_value = claude_reply({}, "refusal")

        with pytest.raises(ConversionUnavailable):
            photo_conversion.read_cotas(JPEG, "image/jpeg")

    def test_an_api_error_is_unavailable(self, client) -> None:
        client.beta.messages.create.side_effect = anthropic.APIConnectionError(
            request=mocker_request()
        )

        with pytest.raises(ConversionUnavailable):
            photo_conversion.read_cotas(JPEG, "image/jpeg")


class TestMissingSides:
    """Qué lado falta: una cota horizontal y una vertical legibles bastan."""

    def test_a_slanted_cota_measures_neither_side(self) -> None:
        reading = cotas_reading(100, 100, (0, 0, 60, 60, 8.5))

        assert photo_conversion.missing_sides(reading) == ["width", "height"]

    def test_both_sides_written(self) -> None:
        reading = cotas_reading(100, 100, (0, 0, 90, 3, 9), (2, 0, 0, 80, 8))

        assert photo_conversion.missing_sides(reading) == []


class TestReadPlanWithMeasures:
    """La IA recibe el ancho y el alto que dio el arquitecto."""

    def test_the_measures_go_in_the_prompt(self, mocker, settings) -> None:
        settings.ANTHROPIC_API_KEY = "test-key"
        fake = mocker.Mock()
        mocker.patch.object(photo_conversion.anthropic, "Anthropic", return_value=fake)
        fake.beta.messages.create.return_value = claude_reply(plan_reading(800, 600))

        photo_conversion.read_plan(
            JPEG, "image/jpeg", measures={"width_m": 12.5, "height_m": 8.0}
        )

        text = fake.beta.messages.create.call_args.kwargs["messages"][0]["content"][1]
        assert "12.5 m wide" in text["text"]
        assert "8.0 m high" in text["text"]
