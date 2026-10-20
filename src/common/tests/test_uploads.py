"""Archivos validados por su contenido, con nombre propio y privados.

Bug iteracion-12 #5 (US-16 · US-102 · US-105 · US-31 · US-54 · US-129). Lo que se
sube se juzga por sus primeros bytes, no por la extensión ni por el tipo que
declara el navegador; se guarda con un nombre que pone el servidor, y el bucket
puede servirse con direcciones firmadas que vencen.
"""

import io
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.exceptions import ValidationError

import core.settings as core_settings
from apps.accounts.services import get_my_organization
from apps.assets.models import PlanAsset
from common.validators import IMAGES, validate_upload

UUID_NAME = re.compile(r"[0-9a-f]{32}\.[a-z0-9]+$")


def png_bytes(size=(4, 4)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="PNG")
    return buffer.getvalue()


HTML = b"<!doctype html><script>alert(document.cookie)</script>"
OBJ = b"# modelo\nmtllib silla.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
GLB = b"glTF\x02\x00\x00\x00" + b"\x00" * 64
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64


class TestValidarPorElContenido:
    """validate_upload lee la firma real del archivo."""

    def test_a_real_image_passes_and_says_what_it_is(self) -> None:
        archivo = SimpleUploadedFile("foto.png", png_bytes(), "image/png")

        assert validate_upload(archivo, allowed=IMAGES, max_bytes=1024**2) == "png"
        assert archivo.tell() == 0

    def test_html_dressed_as_an_image_is_refused(self) -> None:
        archivo = SimpleUploadedFile("foto.png", HTML, "image/png")

        with pytest.raises(ValidationError):
            validate_upload(archivo, allowed=IMAGES, max_bytes=1024**2)

    def test_too_big_is_refused_before_reading_it(self) -> None:
        archivo = SimpleUploadedFile("foto.png", png_bytes(), "image/png")

        with pytest.raises(ValidationError, match="tamaño"):
            validate_upload(archivo, allowed=IMAGES, max_bytes=10)

    def test_an_image_with_too_many_pixels_is_refused(self) -> None:
        archivo = SimpleUploadedFile("foto.png", png_bytes((300, 300)), "image/png")

        with pytest.raises(ValidationError, match="dimensiones"):
            validate_upload(
                archivo, allowed=IMAGES, max_bytes=1024**2, max_pixels=10_000
            )

    def test_svg_is_never_an_image_here(self) -> None:
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'
        archivo = SimpleUploadedFile("logo.svg", svg, "image/svg+xml")

        with pytest.raises(ValidationError):
            validate_upload(archivo, allowed=IMAGES, max_bytes=1024**2)


@pytest.mark.django_db
class TestEvidencia:
    """US-16: la foto de un avance es una imagen de verdad."""

    def _avance(self, user):
        from common.tests.test_cross_account import cuenta_completa

        return cuenta_completa(user)["project"].progresses.first()

    def test_html_declared_as_png_is_refused(self, authenticated_client, user) -> None:
        avance = self._avance(user)

        response = authenticated_client.post(
            f"/api/progresses/{avance.id}/evidence/",
            {"image": SimpleUploadedFile("foto.png", HTML, "image/png")},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not avance.evidences.exists()

    def test_a_photo_is_stored_under_a_name_of_its_own(
        self, authenticated_client, user
    ) -> None:
        avance = self._avance(user)

        authenticated_client.post(
            f"/api/progresses/{avance.id}/evidence/",
            {"image": SimpleUploadedFile("Mi foto (1).png", png_bytes(), "image/png")},
            format="multipart",
        )

        nombre = avance.evidences.get().image.name
        assert nombre.startswith(f"evidence/{user.id}/")
        assert UUID_NAME.search(nombre)
        assert "Mi foto" not in nombre


@pytest.mark.django_db
class TestLogotipo:
    """US-105: el logotipo es una imagen y se guarda con nombre propio."""

    def test_a_logo_gets_a_generated_name(self, authenticated_client, user) -> None:
        authenticated_client.patch(
            "/api/auth/organization/",
            {"logo": SimpleUploadedFile("logo empresa.png", png_bytes(), "image/png")},
            format="multipart",
        )

        nombre = get_my_organization(user=user).logo.name
        assert UUID_NAME.search(nombre)
        assert "empresa" not in nombre


def subir_asset(client, *, path, kind, data, name):
    return client.post(
        "/api/plan-assets/",
        {"path": path, "kind": kind, "file": SimpleUploadedFile(name, data)},
        format="multipart",
    )


@pytest.mark.django_db
class TestArchivosDelEditor:
    """US-102 / US-129: texturas que son imágenes y mallas que son mallas."""

    def test_a_texture_must_be_an_image(self, authenticated_client) -> None:
        response = subir_asset(
            authenticated_client,
            path="sh3t/azulejo.png",
            kind="texture",
            data=HTML,
            name="azulejo.png",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not PlanAsset.objects.exists()

    @pytest.mark.parametrize(
        ("path", "data"),
        [
            ("sh3f/silla.obj", OBJ),
            ("sh3f/silla.mtl", b"newmtl madera\nKd 0.5 0.3 0.1\nmap_Kd madera.jpg\n"),
            ("sh3f/silla.glb", GLB),
            ("sh3f/silla/textura.png", png_bytes()),
            # Las bibliotecas de Sweet Home 3D guardan mallas sin extensión.
            ("sh3f/7/0", OBJ),
        ],
    )
    def test_meshes_materials_and_their_textures_are_accepted(
        self, authenticated_client, path, data
    ) -> None:
        response = subir_asset(
            authenticated_client, path=path, kind="model", data=data, name="x"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert UUID_NAME.search(PlanAsset.objects.get(path=path).file.name)

    @pytest.mark.parametrize(
        ("name", "data"),
        [("silla.obj", HTML), ("silla.obj", EXE), ("silla.pdf", b"%PDF-1.4 x")],
    )
    def test_anything_else_as_a_model_is_refused(
        self, authenticated_client, name, data
    ) -> None:
        response = subir_asset(
            authenticated_client,
            path=f"sh3f/{name}",
            kind="model",
            data=data,
            name=name,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_mesh_is_never_served_as_a_web_page(self, authenticated_client) -> None:
        """Caso de borde - El nombre guardado no hereda la extensión del cliente."""
        subir_asset(
            authenticated_client,
            path="sh3f/silla.html",
            kind="model",
            data=OBJ,
            name="silla.html",
        )

        assert not PlanAsset.objects.get().file.name.endswith(".html")


@pytest.mark.django_db
class TestDocumentosSoloPdf:
    """US-31: lo que sale por correo con la marca de la cuenta es su PDF."""

    @pytest.fixture
    def correo(self, settings, mocker):
        settings.RESEND_API_KEY = "re_test"
        return mocker.patch("common.mail.send_email", return_value=True)

    def enviar(self, client, nombre, data, **extra):
        return client.post(
            "/api/documents/send/",
            {
                "kind": "quote",
                "to": "cliente@correo.mx",
                "file": SimpleUploadedFile(nombre, data, "application/pdf"),
                **extra,
            },
            format="multipart",
        )

    @pytest.mark.parametrize("data", [HTML, EXE, png_bytes()])
    def test_only_a_pdf_can_be_sent(self, authenticated_client, correo, data) -> None:
        response = self.enviar(authenticated_client, "cotizacion.pdf", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        correo.assert_not_called()

    def test_the_attachment_is_named_by_the_server(
        self, authenticated_client, correo
    ) -> None:
        self.enviar(
            authenticated_client,
            "../../factura falsa.exe.pdf",
            b"%PDF-1.4 x",
            reference="COT-0007",
        )

        adjunto = correo.call_args.kwargs["attachments"][0]
        assert adjunto.filename == "cotizacion-COT-0007.pdf"


class TestDireccionesFirmadas:
    """El bucket puede servirse privado, con direcciones que vencen."""

    def _storages(self, **entorno):
        variables = {**os.environ, "DJANGO_SETTINGS_MODULE": "core.settings"}
        variables.update(
            R2_ACCESS_KEY_ID="id",
            R2_SECRET_ACCESS_KEY="secreto",
            R2_BUCKET_NAME="cubeta",
            R2_ENDPOINT_URL="https://cuenta.r2.cloudflarestorage.com",
            R2_PUBLIC_URL="https://media.ejemplo.com",
            **entorno,
        )
        leer = (
            "from django.conf import settings as s;"
            "o = s.STORAGES['default']['OPTIONS'];"
            "print(o['querystring_auth'], o.get('querystring_expire'),"
            " o['custom_domain'])"
        )
        salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [sys.executable, "-c", leer],
            cwd=Path(core_settings.__file__).resolve().parents[1],
            env=variables,
            capture_output=True,
            text=True,
            check=True,
        )
        return salida.stdout.split()

    def test_signed_urls_expire_and_skip_the_public_domain(self) -> None:
        assert self._storages(R2_SIGNED_URLS="True") == ["True", "3600", "None"]

    def test_without_the_switch_the_public_domain_stays(self) -> None:
        assert self._storages(R2_SIGNED_URLS="False") == [
            "False",
            "None",
            "media.ejemplo.com",
        ]
