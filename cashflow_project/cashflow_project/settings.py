from pathlib import Path
import os

# ── python-dotenv: load .env file if present ─────────────────────────────────
# Install: pip install python-dotenv
# On the droplet, create /path/to/project/.env with your secrets.
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env'))

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Core security ─────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-change-this-in-production-xxxxxxxxxxxxxxxxxxxx'
)

DEBUG = os.environ.get('DEBUG', 'False').lower() in ('1', 'true', 'yes')

# Comma-separated list in .env: ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
_allowed = os.environ.get('ALLOWED_HOSTS', '*')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'cashflow.apps.CashflowConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cashflow_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'cashflow_project' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'cashflow_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Static files ──────────────────────────────────────────────────────────────
# STATIC_URL  : URL prefix served by nginx / whitenoise
# STATIC_ROOT : where `collectstatic` copies everything (nginx serves this dir)
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'   # nginx: alias /path/to/project/staticfiles/

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Auth redirects ────────────────────────────────────────────────────────────
LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/cashflow/'
LOGOUT_REDIRECT_URL = '/login/'

# Session security — cookies expire when browser closes, 8-hour max
SESSION_COOKIE_AGE      = 60 * 60 * 8   # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# ── Odoo connection settings ──────────────────────────────────────────────────
# Use the domain root only — do NOT include /odoo in the URL.

ODOO_URL=os.environ['ODOO_URL']
ODOO_DB=os.environ['ODOO_DB']
ODOO_USERNAME=os.environ['ODOO_USERNAME']
ODOO_PASSWORD=os.environ['ODOO_PASSWORD'] # Use API key, not password in production

# Cache timeout for Odoo data (seconds)
ODOO_CACHE_TIMEOUT = int(os.environ.get('ODOO_CACHE_TIMEOUT', 300))



