"""Réglages Django de GestiStock.

Les paramètres propres à chaque poste (mot de passe PostgreSQL, clé secrète…)
se trouvent dans le fichier backend/.env (voir .env.exemple).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-seulement-a-changer-en-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Hébergement sur Render (12/10/2026) : Render fournit l'adresse publique du site dans RENDER_EXTERNAL_HOSTNAME.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
# Interface React construite (npm run build) : servie par Django lui-même en ligne (même adresse que l'API).
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "stock",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# WhiteNoise sert les fichiers de l'interface et de l'administration en ligne (ignoré s'il n'est pas installé sur le poste).
try:
    import whitenoise  # noqa: F401
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    _WHITENOISE = True
except ImportError:
    _WHITENOISE = False

ROOT_URLCONF = "gestistock.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "gestistock.wsgi.application"

# Base de données : PostgreSQL uniquement (décision du 12/10/2026 : plus de SQLite, même en développement).
# Les réglages de connexion sont dans backend/.env (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT).
if os.environ.get("DB_ENGINE", "").strip().lower() == "sqlite":
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "SQLite n'est plus utilisé par GestiStock : supprimez la ligne DB_ENGINE de backend/.env "
        "(ou lancez passer-a-postgresql.bat).")
if os.environ.get("DATABASE_URL"):
    # En ligne (Render + Neon, 12/10/2026) : une seule variable DATABASE_URL, donnée par Neon (connexion chiffrée).
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(
        os.environ["DATABASE_URL"], conn_max_age=600, conn_health_checks=True, ssl_require=True)}
    # Compatible avec l'adresse « pooled » de Neon (PgBouncer).
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "gestistock"),
            "USER": os.environ.get("DB_USER", "gestistock"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

# Connexion : l'identifiant est accepté sans tenir compte des majuscules (« haja » = « Haja »),
# dans GestiStock comme dans l'administration Django.
AUTHENTICATION_BACKENDS = ["stock.auth.IdentifiantSansMajuscules"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Indian/Antananarivo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # rempli par « collectstatic » lors de la mise en ligne
if _WHITENOISE:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
# L'interface construite (frontend/dist : index.html, assets/…) est servie à la racine du site.
if FRONTEND_DIST.exists():
    WHITENOISE_ROOT = FRONTEND_DIST
    WHITENOISE_INDEX_FILE = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Comptes en place depuis le 11/10/2026 : il faut être connecté pour tout appel (sauf connexion).
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "stock.permissions.gestion_erreurs",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}

# Session : déconnexion à la fermeture du navigateur, et au plus tard après 10 heures.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 10 * 3600

# L'interface (port 3000) transmet les appels à Django (port 8000) : on accepte cette origine pour la protection CSRF.
CSRF_TRUSTED_ORIGINS = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000").split(",")
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

if not DEBUG:
    # En ligne : connexion HTTPS uniquement (Render termine le HTTPS devant Django).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    if SECRET_KEY.startswith("dev-seulement"):
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("DJANGO_SECRET_KEY manquante : obligatoire en ligne (DJANGO_DEBUG=0).")

# ---------------------------------------------------------------- Emails (11/10/2026)
# Désactivés le 11/10 à 22 h 15 à la demande de l'utilisateur : le Responsable Logistique est prévenu dans l'application
# (compteur sur le menu « À viser »). Pour les réactiver plus tard : GESTISTOCK_EMAILS=1 dans backend/.env.
GESTISTOCK_EMAILS = os.environ.get("GESTISTOCK_EMAILS", "0") == "1"
# Le Responsable Logistique est prévenu par email quand une réquisition attend son visa.
# Envoi par Gmail : EMAIL_HOST_USER = l'adresse Gmail, EMAIL_HOST_PASSWORD = un « mot de passe d'application »
# (à saisir avec outils\configurer-email.bat). Tant qu'il n'y a pas de mot de passe, les emails ne partent pas :
# ils sont enregistrés comme fichiers dans backend/emails-non-envoyes (pour vérifier leur contenu).
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "").replace(" ", "")  # Google l'affiche par groupes de 4
EMAIL_TIMEOUT = 20  # secondes
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or (
    f"GestiStock HBC <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "GestiStock HBC <gestistock@localhost>")
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    EMAIL_FILE_PATH = BASE_DIR / "emails-non-envoyes"
# Destinataire temporaire : s'il est rempli, les emails vont à cette adresse au lieu de celles des comptes Responsable Logistique.
GESTISTOCK_EMAIL_TEMPORAIRE = os.environ.get("GESTISTOCK_EMAIL_TEMPORAIRE", "").strip()
# Adresse de l'application, pour le lien de l'email (à changer lors de l'hébergement, ex. https://stock.hbc-mg.com).
GESTISTOCK_ADRESSE = (os.environ.get("GESTISTOCK_ADRESSE")
                      or (f"https://{RENDER_EXTERNAL_HOSTNAME}" if RENDER_EXTERNAL_HOSTNAME else "http://127.0.0.1:3000")).rstrip("/")
