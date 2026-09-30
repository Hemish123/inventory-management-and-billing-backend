"""
Django settings for MSME PayTrack project.
"""
import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-key-change-in-production')

DEBUG = False

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    # Local apps
    'apps.authentication',
    'apps.companies',
    'apps.core',
    'apps.customers',
    'apps.products',
    'apps.billing',
    'apps.stock',
    'apps.purchases',
    'apps.reports',
    'drf_spectacular',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# if DEBUG:
#     DATABASES = {
#         'default': {
#             'ENGINE': 'django.db.backends.sqlite3',
#             'NAME': BASE_DIR / 'db.sqlite3',
#         }
#     }
# else:
#     CONNECTION_STRING = os.environ.get('AZURE_POSTGRESQL_CONNECTIONSTRING', '')
#     if CONNECTION_STRING:
#         conn_str_params = {pair.split('=')[0]: pair.split('=')[1] for pair in CONNECTION_STRING.split(' ') if '=' in pair}

#         DATABASES = {
#             'default': {
#                 'ENGINE': 'django.db.backends.postgresql',
#                 'NAME': conn_str_params.get('dbname', ''),
#                 'HOST': conn_str_params.get('host', ''),
#                 'USER': conn_str_params.get('user', ''),
#                 'PASSWORD': conn_str_params.get('password', ''),
#             }
#         }
#     else:
#         # Fallback to avoid crashes if ENV var is missing
#         DATABASES = {
#             'default': {
#                 'ENGINE': 'django.db.backends.sqlite3',
#                 'NAME': BASE_DIR / 'db.sqlite3',
#             }
#         }


if DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

else:
    import re
    CONNECTION_STRING = os.environ.get('AZURE_POSTGRESQL_CONNECTIONSTRING', '')

    # ✅ safer parsing (handles special chars)
    conn_str_params = dict(re.findall(r'(\w+)=([^\s]+)', CONNECTION_STRING))

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': conn_str_params.get('dbname', 'postgres'),
            'HOST': conn_str_params.get('host'),
            'USER': conn_str_params.get('user'),
            'PASSWORD': conn_str_params.get('password'),
            'PORT': conn_str_params.get('port', '5432'),   # ✅ added
            'OPTIONS': {
                'sslmode': 'require',                     # ✅ VERY IMPORTANT
            },
        }
    }

ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Custom user model
AUTH_USER_MODEL = 'authentication.CustomUser'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if not DEBUG:
    # In production, use Azure Blob Storage for Media files
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
        "media": {
            "BACKEND": "storages.backends.azure_storage.AzureStorage",
            "OPTIONS": {
                "account_name": os.environ.get('AZURE_ACCOUNT_NAME'),
                "account_key": os.environ.get('AZURE_ACCOUNT_KEY'),
                "azure_container": os.environ.get('AZURE_CONTAINER'),
                "expiration_secs": None,
            },
        },
    }
    # Tell Django to use the 'media' storage backend for media files
    # Actually, for media, Django 4.2+ uses STORAGES['default'] for file fields by default unless specified.
    # To override the default storage for FileFields/ImageFields:
    STORAGES["default"] = STORAGES["media"]
    
    AZURE_ACCOUNT_NAME = os.environ.get('AZURE_ACCOUNT_NAME')
    AZURE_ACCOUNT_KEY = os.environ.get('AZURE_ACCOUNT_KEY')
    AZURE_CONTAINER = os.environ.get('AZURE_CONTAINER')
    AZURE_URL_EXPIRATION_SECS = None
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'utils.exceptions.custom_exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'utils.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'MSME RetailTrack API',
    'DESCRIPTION': 'API documentation for the Retail POS and Inventory Management system.',
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# JWT Settings
ACCESS_TOKEN_LIFETIME = 36500
REFRESH_TOKEN_LIFETIME = 36500

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=ACCESS_TOKEN_LIFETIME),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=REFRESH_TOKEN_LIFETIME),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = ['http://localhost:5173','https://msmepaytrackfrontend-eza8erfadvgdbha0.centralindia-01.azurewebsites.net', 'https://gray-sea-0ec486900.7.azurestaticapps.net', 'https://retailtrack.jmstech.co', 'https://api.retailtrack.jmstech.co']
CORS_ALLOW_CREDENTIALS = True

# Azure OpenAI — removed during RetailTrack refactor

# File upload
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Email Settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = 'JMS Advisory <resumate1nfo1@gmail.com>'

# Company Info (used in bill PDF generation)
COMPANY_NAME = 'JMS Advisory'
COMPANY_ADDRESS = '401 Anand mangal 3, Ahmedabad, Gujarat 380015'
COMPANY_GST = '24BTIPD4800M1ZT'
COMPANY_PHONE = '+91 92744 25300'
COMPANY_EMAIL = 'info@jmsadvisory.in'

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
if DEBUG:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} [{name}] {message}',
                'style': '{',
            },
            'simple': {
                'format': '{levelname} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': BASE_DIR / 'scraper.log',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'scrapers': {
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': False,
            },
            'django': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': True,
            },
        },
    }
else:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} {module} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'file': {
                'level': 'ERROR',
                'class': 'logging.FileHandler',
                'filename': '/home/site/wwwroot/django_errors.log' if os.path.exists('/home/site/wwwroot') else BASE_DIR / 'django_errors.log',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'django': {
                'handlers': ['file'],
                'level': 'ERROR',
                'propagate': False,
            },
        },
    }

CSRF_TRUSTED_ORIGINS = [
    "https://msmebackendjms-gcgbh3f4dndea6dz.centralindia-01.azurewebsites.net",
    "https://inventorymanagementbilling-gpdah6c9gug3a8au.centralindia-01.azurewebsites.net",
    "https://gray-sea-0ec486900.7.azurestaticapps.net",
    "https://retailtrack.jmstech.co",
    "https://api.retailtrack.jmstech.co"
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True