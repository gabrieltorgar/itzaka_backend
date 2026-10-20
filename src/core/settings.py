"""Django settings for CUOTREKA backend.

Modular settings: this file holds Django's own config and initializes
``environ`` once. STATIC/MEDIA/security live in ``core.env``; each third-party
library with significant config gets its own ``settings_<name>.py``.
"""

from datetime import timedelta
from pathlib import Path

import environ

# BASE_DIR = repo root (parents: settings.py -> core -> src -> repo)
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "dev-insecure-change-me"),
    ALLOWED_HOSTS=(list, ["*"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    LOG_DIR=(str, str(BASE_DIR / "tmp" / "logs")),
    OTP_UNIVERSAL_CODE=(str, "123456"),
    OTP_TTL_MINUTES=(int, 10),
    # Intentos fallidos que aguanta un código antes de morir (iteracion-12).
    OTP_MAX_ATTEMPTS=(int, 5),
    THROTTLE_ANON=(str, "60/min"),
    THROTTLE_USER=(str, "300/min"),
    # Long enough to keep an active session working; a refresh token silently
    # renews access so the user is not logged out mid-use (see /auth/refresh/).
    ACCESS_TOKEN_LIFETIME_MINUTES=(int, 30),
    REFRESH_TOKEN_LIFETIME_DAYS=(int, 7),
)

# Load .env from core/ if present (optional — all vars have safe defaults).
_env_file = BASE_DIR / "src" / "core" / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))

# Vercel injects VERCEL=1 in build and runtime; harden defaults there
# (DEBUG off by default and the deployment's own hostnames trusted).
ON_VERCEL = env.bool("VERCEL", default=False)

DEBUG = env.bool("DEBUG", default=not ON_VERCEL)
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# On Vercel, trust the deployment's own hostnames so ALLOWED_HOSTS, CSRF and the
# admin login keep working on preview/production URLs without per-deploy config.
_VERCEL_HOSTS = [
    host
    for host in (
        env.str("VERCEL_URL", default=""),
        env.str("VERCEL_BRANCH_URL", default=""),
        env.str("VERCEL_PROJECT_PRODUCTION_URL", default=""),
    )
    if host
]
if _VERCEL_HOSTS:
    ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS + _VERCEL_HOSTS))
    CSRF_TRUSTED_ORIGINS = list(
        dict.fromkeys(CSRF_TRUSTED_ORIGINS + [f"https://{h}" for h in _VERCEL_HOSTS])
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "storages",
    # Local apps
    "apps.accounts",
    "apps.catalog",
    "apps.clients",
    "apps.quotes",
    "apps.projects",
    "apps.payments",
    "apps.leads",
    "apps.planner",
    "apps.staff",
    "apps.dashboard",
    "apps.assets",
    "apps.documents",
    "apps.legal",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files (admin/DRF) from the serverless function;
    # must sit right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---
REST_FRAMEWORK = {
    # El access llega en una cookie HttpOnly (common/auth_cookies.py); la
    # cabecera Authorization sigue sirviendo a clientes de API.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "common.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Límites por dirección o por cuenta en todo, y uno propio en cada puerta
    # pública: sin tope, un código de seis dígitos se adivina probando.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON"),
        "user": env("THROTTLE_USER"),
        "login": "10/min",
        "signup": "10/hour",
        "otp": "5/min",
        "password_reset": "5/hour",
        "contact": "5/hour",
        "documents": "30/hour",
    },
    # Detrás del proxy de Vercel, la dirección real es la del X-Forwarded-For.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=1),
    "EXCEPTION_HANDLER": "common.exceptions.exception_handler",
}

# --- Caché compartida (estado de los límites) ---
# En Vercel cada invocación puede ser otra instancia: una caché en memoria no
# cuenta nada. La tabla vive en la misma base y la crea el build
# (createcachetable); las pruebas usan memoria local (conftest.py).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cuotreka_cache",
    }
}

# --- SimpleJWT (sesión en cookies HttpOnly, iteracion-12) ---
# Media hora de access y una semana de refresh como máximo, aunque el entorno
# pida más: una sesión robada vale poco y por poco tiempo. El refresh rota en
# cada renovación y el usado queda en la lista negra; salir lo anula.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=min(env("ACCESS_TOKEN_LIFETIME_MINUTES"), 30)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=min(env("REFRESH_TOKEN_LIFETIME_DAYS"), 7)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
}

# --- OTP (universal code for the MVP; real SMS/WhatsApp integration later) ---
# Con correo configurado, una cuenta con correo recibe un código propio y este
# deja de servirle; sigue siendo el de las cuentas que sólo tienen teléfono,
# porque todavía no hay SMS por donde mandarles el suyo.
OTP_UNIVERSAL_CODE = env("OTP_UNIVERSAL_CODE")
# Y sólo donde se pidió: en local (DEBUG) sí; en producción hay que pedirlo a
# propósito, para que una llave de correo que falte no abra todas las cuentas.
OTP_UNIVERSAL_CODE_ENABLED = env.bool("OTP_UNIVERSAL_CODE_ENABLED", default=DEBUG)
OTP_MAX_ATTEMPTS = env("OTP_MAX_ATTEMPTS")

# --- reCAPTCHA v3 en los formularios públicos (common/recaptcha.py) ---
# Se verifica en cuanto hay llave secreta: sin ella no se cierra la puerta a
# todos. La llave del sitio vive en el frontend (VITE_RECAPTCHA_SITE_KEY).
RECAPTCHA_SECRET_KEY = env.str("RECAPTCHA_SECRET_KEY", default="").strip()
RECAPTCHA_ENABLED = env.bool("RECAPTCHA_ENABLED", default=bool(RECAPTCHA_SECRET_KEY))
RECAPTCHA_MIN_SCORE = env.float("RECAPTCHA_MIN_SCORE", default=0.5)
RECAPTCHA_HOSTNAMES = env.list(
    "RECAPTCHA_HOSTNAMES", default=["cuotreka.vercel.app", "localhost"]
)

# Tope de lo que puede viajar adjunto en un correo. Un PDF de cotización pesa
# kilobytes; uno con fotos de avance, no tanto como para pagarlo en base64.
DOCUMENT_EMAIL_MAX_BYTES = env.int("DOCUMENT_EMAIL_MAX_BYTES", default=8 * 1024 * 1024)

# --- Resend (correo saliente por su API HTTP, no por el mailer de Django) ---
# Se recortan: un salto de línea o un espacio pegado al pegar el valor
# invalida la llave —Resend contesta 401— sin que se vea en ningún lado.
RESEND_API_KEY = env.str("RESEND_API_KEY", default="").strip()
RESEND_FROM = env.str("RESEND_FROM", default="CUOTREKA <onboarding@resend.dev>").strip()
# A dónde llevan los enlaces de los correos: la aplicación, no la API.
APP_BASE_URL = env.str("APP_BASE_URL", default="https://presuplano.vercel.app")

# Tope del documento de un plano. Una textura suelta y el plano de fondo
# escaneado viajan dentro del JSON, que es lo que puede engordarlo.
PLAN_MAX_BYTES = env.int("PLAN_MAX_BYTES", default=4 * 1024 * 1024)

# Tope por archivo del editor (una textura, una malla). Lo que no cabe en el
# documento del plano vive en el bucket, pero tampoco sin límite.
PLAN_ASSET_MAX_BYTES = env.int("PLAN_ASSET_MAX_BYTES", default=10 * 1024 * 1024)

# --- Foto de un plano en papel → plano editable (US-129) ---
# La lee Claude con visión. Sin llave la conversión responde «no disponible»
# en vez de romperse; también se recorta, como la de Resend.
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="").strip()
PHOTO_PLAN_MODEL = env.str("PHOTO_PLAN_MODEL", default="claude-opus-5-5")
# Cada foto cuesta dinero: cinco por cuenta al día (decidido en GATE PROPUESTA).
PHOTO_PLAN_DAILY_LIMIT = env.int("PHOTO_PLAN_DAILY_LIMIT", default=5)
# El navegador la comprime antes de enviarla; Vercel no acepta cuerpos de más
# de ~4.5 MB en una función, así que lo que pase de 4 MB ni se intenta.
PHOTO_PLAN_MAX_BYTES = env.int("PHOTO_PLAN_MAX_BYTES", default=4 * 1024 * 1024)
OTP_TTL_MINUTES = env("OTP_TTL_MINUTES")

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
# La SPA escribe con la cookie de la sesión y su token CSRF: el origen de la
# aplicación tiene que ser de confianza para la comprobación CSRF de Django.
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS + CORS_ALLOWED_ORIGINS))

# STATIC/MEDIA + security + logging + storages (media on R2 in production)
from .env import *  # noqa: E402,F403
from .settings_storages import *  # noqa: E402,F403
