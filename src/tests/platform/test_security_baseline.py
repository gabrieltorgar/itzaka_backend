"""Platform baseline: security settings and static scans (TDD-B01, iteracion-12 #8).

Not tied to a user story: encodes the always-on part of the security criteria
(secure DRF defaults, throttling on a shared cache, max_page_size, hashers and
validators, cookie and header settings, the production HTTPS block) and three
static scans over ``src/apps/`` and ``src/common/``. A failing scan prints
``file:line``: fix the code, never weaken the test.
"""

import ast
from pathlib import Path

from django.conf import settings as dj_settings
from django.utils.module_loading import import_string

import core.settings as core_settings

SRC = Path(__file__).resolve().parents[2]  # src/
SCANNED = (SRC / "apps", SRC / "common")


def _py_files():
    return [
        path
        for root in SCANNED
        for path in root.rglob("*.py")
        if "migrations" not in path.parts and "tests" not in path.parts
    ]


# ---------- settings [SEC-04, SEC-05, SRV-01, SRV-02, BOT-03, VAL-06]


def test_drf_defaults_are_secure():
    rf = dj_settings.REST_FRAMEWORK
    assert "rest_framework.permissions.IsAuthenticated" in rf[
        "DEFAULT_PERMISSION_CLASSES"
    ]
    assert rf.get("DEFAULT_THROTTLE_CLASSES"), "throttling must be on by default"
    for scope in ("anon", "user", "login", "otp", "password_reset"):
        assert scope in rf["DEFAULT_THROTTLE_RATES"], f"missing throttle rate '{scope}'"


def test_pagination_has_a_max_page_size():
    paginator = import_string(dj_settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"])
    assert getattr(paginator, "max_page_size", None), "pagination needs max_page_size"


def test_cache_is_shared_outside_the_tests():
    # The suite swaps in a local-memory cache (conftest.py); what ships is read
    # from the settings module itself.
    backend = core_settings.CACHES["default"]["BACKEND"]
    assert "locmem" not in backend.lower(), "throttling needs a shared cache"


def test_password_hashing_and_validators():
    assert dj_settings.PASSWORD_HASHERS[0].startswith("django.contrib.auth.hashers.")
    assert len(dj_settings.AUTH_PASSWORD_VALIDATORS) >= 4


def test_cookie_csrf_and_header_settings():
    assert dj_settings.SESSION_COOKIE_HTTPONLY is True
    assert dj_settings.SESSION_COOKIE_SAMESITE in ("Lax", "Strict")
    assert dj_settings.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert dj_settings.X_FRAME_OPTIONS == "DENY"
    assert dj_settings.SECURE_REFERRER_POLICY
    assert dj_settings.USE_TZ is True
    assert dj_settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    assert dj_settings.DATA_UPLOAD_MAX_MEMORY_SIZE <= 10 * 1024 * 1024
    assert getattr(dj_settings, "CORS_ALLOW_ALL_ORIGINS", False) is False


def test_production_https_settings_are_declared():
    """The production block is checked as source: the suite runs with DEBUG on.

    This project keeps CSRF_TRUSTED_ORIGINS in settings.py (it merges the
    Vercel hosts and the CORS origins); the rest lives in core/env.py.
    """
    source = (SRC / "core" / "env.py").read_text(encoding="utf-8") + (
        SRC / "core" / "settings.py"
    ).read_text(encoding="utf-8")
    for name in (
        "SECURE_PROXY_SSL_HEADER",
        "SECURE_SSL_REDIRECT",
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "SECURE_HSTS_SECONDS",
        "CSRF_TRUSTED_ORIGINS",
    ):
        assert name in source, f"core settings do not declare {name}"


# ---------- static scans [SEC-03, API-01, CRD-01]


def _assign_value(node, target):
    for n in ast.walk(node):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == target for t in n.targets
        ):
            yield n


def test_serializers_list_fields_explicitly():
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        metas = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        for cls in [n for n in metas if n.name == "Meta"]:
            for a in _assign_value(cls, "fields"):
                if isinstance(a.value, ast.Constant) and a.value.value == "__all__":
                    offenders.append(f"{path.relative_to(SRC)}:{a.lineno} '__all__'")
            for a in _assign_value(cls, "exclude"):
                offenders.append(f"{path.relative_to(SRC)}:{a.lineno} exclude")
    assert not offenders, "explicit serializer fields required:\n" + "\n".join(
        offenders
    )


def _is_dynamic_string(node):
    return (
        isinstance(node, ast.JoinedStr)
        or (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)))
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
        )
    )


def test_raw_sql_is_parameterized():
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ]
        for call in calls:
            where = f"{path.relative_to(SRC)}:{call.lineno}"
            if call.func.attr == "extra":
                offenders.append(f"{where} .extra() is prohibited")
            if (
                call.func.attr in ("execute", "raw", "executemany")
                and call.args
                and _is_dynamic_string(call.args[0])
            ):
                offenders.append(f"{where} SQL built from a string expression")
    assert not offenders, "use separated parameters:\n" + "\n".join(offenders)


def test_no_password_or_token_in_logs():
    offenders = []
    for path in _py_files():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            if "logger." in low and any(
                w in low for w in ("password", "token", "secret", "otp_code")
            ):
                offenders.append(f"{path.relative_to(SRC)}:{i}")
    assert not offenders, "never log credentials:\n" + "\n".join(offenders)
