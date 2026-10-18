import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default='False'):
    return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


DEBUG = env_bool('DEBUG', 'True')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        # Локальная разработка: допустим временный ключ
        SECRET_KEY = 'django-insecure-dev-key-change-in-production'
    else:
        # Прод: тихий небезопасный ключ недопустим
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY must be set when DEBUG=False. '
            'Set it in .env or environment variables.'
        )

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'django_filters',
    'cinema',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cinema_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cinema.context_processors.booking_limits',
            ],
        },
    },
]

WSGI_APPLICATION = 'cinema_project.wsgi.application'

# БД: DATABASE_URL имеет приоритет; иначе USE_SQLITE/POSTGRES_* (legacy)
_default_db_url = (
    f'sqlite:///{BASE_DIR / "db.sqlite3"}'
    if env_bool('USE_SQLITE', 'True')
    else (
        f"postgres://{os.getenv('POSTGRES_USER', 'cinema_user')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'cinema_pass')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'cinema_db')}"
    )
)
DATABASES = {
    'default': dj_database_url.config(
        default=_default_db_url,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'cinema.User'

LANGUAGE_CODE = 'ru'
TIME_ZONE = os.getenv('TIME_ZONE', 'Asia/Almaty')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Безопасность (применяется в проде) ──────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', 'True')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
else:
    SECURE_SSL_REDIRECT = False
    X_FRAME_OPTIONS = 'DENY'

# ── DRF ─────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '120/min',
        'auth': '10/min',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'cinema.exceptions.api_exception_handler',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'АИС «Аврора» API',
    'DESCRIPTION': 'API кинотеатра: афиша, бронирование, билеты, платежи, дашборд',
    'VERSION': '1.0.0',
    'ENUM_NAME_OVERRIDES': {
        'MovieStatus': 'cinema.models.Movie.STATUS_CHOICES',
        'BookingStatus': 'cinema.models.Booking.STATUS_CHOICES',
        'TicketStatus': 'cinema.models.Ticket.STATUS_CHOICES',
        'PaymentStatus': 'cinema.models.Payment.STATUS_CHOICES',
        'PaymentMethod': 'cinema.models.Payment.METHOD_CHOICES',
        'UserRole': 'cinema.models.User.ROLE_CHOICES',
    },
}

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'profile'
LOGOUT_REDIRECT_URL = 'home'

SESSION_COOKIE_AGE = 86400
SESSION_SAVE_EVERY_REQUEST = True

# ── Бизнес-лимиты ───────────────────────────────────────
BOOKING_MAX_SEATS = env_int('BOOKING_MAX_SEATS', 10)
BOOKING_HOLD_MINUTES = env_int('BOOKING_HOLD_MINUTES', 15)
SESSION_BUFFER_MINUTES = env_int('SESSION_BUFFER_MINUTES', 20)

# ── Платёжный шлюз (Kaspi/Халык) ────────────────────────
# Секрет HMAC-SHA256 для подписи webhook'ов провайдера.
# В проде задаётся через PAYMENT_WEBHOOK_SECRET; по умолчанию — SECRET_KEY.
PAYMENT_WEBHOOK_SECRET = os.getenv('PAYMENT_WEBHOOK_SECRET', '') or SECRET_KEY

# ── Логирование ─────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'cinema': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
