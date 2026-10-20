"""Content-Security-Policy con una excepción acotada al admin (iteracion-13)."""

from csp.constants import UNSAFE_EVAL, UNSAFE_INLINE
from csp.middleware import CSPMiddleware

ADMIN_PREFIX = "/admin/"

#: Lo que el admin de Unfold necesita: Alpine.js evalúa sus expresiones y la
#: interfaz pone estilos en línea. Se suma a la política global sólo bajo
#: /admin/; la API y todo lo demás siguen sin nada inseguro.
ADMIN_POLICY_UPDATE = {
    "script-src": [UNSAFE_EVAL],
    "style-src": [UNSAFE_INLINE],
}


class ScopedCSPMiddleware(CSPMiddleware):
    """La CSP global (settings_csp.py), ampliada sólo para el admin."""

    def process_response(self, request, response):
        if request.path.startswith(ADMIN_PREFIX) and not hasattr(
            response, "_csp_update"
        ):
            response._csp_update = ADMIN_POLICY_UPDATE
        return super().process_response(request, response)
