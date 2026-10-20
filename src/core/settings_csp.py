"""Content-Security-Policy de lo que la API sirve como HTML (iteracion-12 #6).

La API responde JSON, pero el admin y la API navegable de DRF son páginas: la
política es la segunda barrera si algo inyectara un script en ellas. Nada en
línea ni de fuera; las imágenes pueden venir del bucket (logotipos, fotos).
"""

from csp.constants import NONE, SELF

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF],
        "style-src": [SELF],
        "img-src": [SELF, "data:", "https:"],
        "font-src": [SELF, "data:"],
        "connect-src": [SELF],
        "object-src": [NONE],
        "base-uri": [SELF],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
    }
}
