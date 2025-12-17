# config/settings.py
# إعدادات مشروع SamiLink — آمنة وحديثة، تدعم .env، وتوافق التحليل المعتمد

from __future__ import annotations
from pathlib import Path
import os
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# =========================
# تحميل .env (اختياري)
# =========================
if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv  # python-dotenv
        load_dotenv(ENV_FILE)
    except Exception:
        # في التطوير فقط نطبع ملاحظة؛ لا نُفشل التشغيل
        if os.getenv("DEBUG", "True") == "True":
            print("[settings] Warning: .env not fully loaded")

# =========================
# أدوات قراءة البيئة
# =========================
def env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, str(default))
    return val.lower() in ("1", "true", "yes", "on")

def env_list(key: str, default: str = "") -> list[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]

def env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default

# =========================
# القيم الأساسية
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")   # غيِّرها في الإنتاج
DEBUG = env_bool("DEBUG", False)                         # افتراضيًا إيقاف DEBUG
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# =========================
# التطبيقات
# =========================
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # طرف ثالث
    "rest_framework",
    "django_filters",
    "widget_tweaks",
    # "corsheaders",  # فعّل ثم أضف إلى MIDDLEWARE إذا احتجت CORS

    # تطبيقات المشروع
    "accounts",
    "profiles",
    "marketplace",
    "agreements.apps.AgreementsConfig",
    "finance",
    "disputes",
    "uploads",
    "notifications",
    "core",
    "website",
    "dashboard",
    "django.contrib.humanize",
]

# دعم اختياري لقنوات الويب (Messaging/WS) عبر Channels إذا USE_CHANNELS=true
USE_CHANNELS = env_bool("USE_CHANNELS", True)
if USE_CHANNELS:
    INSTALLED_APPS.append("channels")

AUTH_USER_MODEL = "accounts.User"
PHONE_DEFAULT_COUNTRY_CODE = os.getenv("PHONE_DEFAULT_COUNTRY_CODE", "966")

# =========================
# الوسطاء (Middleware)
# =========================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # "corsheaders.middleware.CorsMiddleware",  # إذا فعّلت corsheaders
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # إخفاء بيانات العميل أثناء نافذة العروض (ميدل وير مخصّص بالمشروع)
    "marketplace.middleware.ContactMaskingMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application" if USE_CHANNELS else "config.wsgi.application"

# =========================
# القوالب
# =========================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",

                # ✅ Context Processor عام للإشعارات (يمرّر unread_count + latest)
                # أنشئه في: core/notifications/context_processors.py
                "core.notifications.context_processors.notifications_context",
            ],
        },
    },
]

# =========================
# قواعد البيانات
# =========================
# يدعم DATABASE_URL (مثل Render/DO) أو ضبط صريح
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_ENGINE = os.getenv("DB_ENGINE", "").lower()

if DATABASE_URL:
    try:
        import dj_database_url  # dj-database-url
        DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=env_int("DB_CONN_MAX_AGE", 60))}
    except Exception:
        # fallback إلى Postgres/SQLite أدناه لو لم تتوفر الحزمة
        DATABASE_URL = ""  # نُسقطه ليأخذ الفرع التالي
if not DATABASE_URL:
    if DB_ENGINE == "postgres":
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.getenv("DB_NAME", "samilink"),
                "USER": os.getenv("DB_USER", "postgres"),
                "PASSWORD": os.getenv("DB_PASSWORD", ""),
                "HOST": os.getenv("DB_HOST", "localhost"),
                "PORT": os.getenv("DB_PORT", "5432"),
                "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
                "OPTIONS": {
                    # "sslmode": "require",
                },
            }
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }

# =========================
# الكاش (Redis اختياري)
# =========================
REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "TIMEOUT": env_int("CACHE_TIMEOUT", 300),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": os.getenv("CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
            "LOCATION": "samilink-local",
            "TIMEOUT": env_int("CACHE_TIMEOUT", 300),
        }
    }

# =========================
# قنوات الويب (Channels) — اختياري
# =========================
if USE_CHANNELS:
    # طبقة قنوات عبر Redis إن توافرت؛ وإلا InMemory (للتطوير)
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer" if REDIS_URL else "channels.layers.InMemoryChannelLayer",
            **({"CONFIG": {"hosts": [REDIS_URL]}} if REDIS_URL else {}),
        }
    }

# =========================
# التدويل والوقت
# =========================
LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# =========================
# الملفات الساكنة والإعلام
# =========================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise (مُوصى به في Django 5 عبر STORAGES)
STORAGES = {
    "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_KEEP_ONLY_HASHED_FILES = True

# Cloudinary
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME', 'dnob4uzo6'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY', '323685142587988'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET', 't1J7Pfi-7Rh1i6n-DftrxuP5Kg8'),
}

# =========================
# سياسة السوق/المنصّة (من التحليل)
# =========================
# ملاحظة: استخدم نفس الاسم في الكود: OFFERS_WINDOW_DAYS
OFFERS_WINDOW_DAYS = env_int("OFFERS_WINDOW_DAYS", 5)   # نافذة استقبال العروض (أيام)
ONE_OFFER_PER_TECH = env_bool("ONE_OFFER_PER_TECH", True)  # عرض واحد لكل تقني على كل طلب
HIDE_CLIENT_CONTACT_DURING_OFFERS = env_bool("HIDE_CLIENT_CONTACT_DURING_OFFERS", True)

# أنماط تنظيف وسائل الاتصال من نصوص الطلب/الوصف عندما تكون نافذة العروض فعّالة
CONTACT_SANITIZATION_PATTERNS = [
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"(?<!\d)(?:\+?\d[\d\s\-]{7,}\d)",
    r"(?:https?://|www\.)\S+",
    r"(?:@|at\s+)?[A-Za-z0-9_]{3,}",
]

# الرسوم والضريبة
PLATFORM_FEE_DEFAULT = float(os.getenv("PLATFORM_FEE_DEFAULT", "0.10"))  # 10%
VAT_RATE = float(os.getenv("VAT_RATE", "0.15"))                           # 15%

# بيانات رسمية تظهر في الاتفاقية/الفواتير
PLATFORM_OFFICIAL_NAME = os.getenv("PLATFORM_OFFICIAL_NAME", "منصة سامي لينك")
PLATFORM_CR_NUMBER = os.getenv("PLATFORM_CR_NUMBER", "7050062491")

# نزاعات: تجميد الصرف تلقائيًا
FREEZE_PAYOUT_ON_DISPUTE = env_bool("FREEZE_PAYOUT_ON_DISPUTE", True)

# =========================
# الأمان
# =========================
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_HTTPONLY = env_bool("SESSION_COOKIE_HTTPONLY", True)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_HTTPONLY = env_bool("CSRF_COOKIE_HTTPONLY", True)
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = os.getenv("REFERRER_POLICY", "strict-origin-when-cross-origin")
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", True)

# =========================
# البريد
# =========================
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.example.com")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 30)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "SamiLink <no-reply@samilink.sa>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
ADMINS = [("GM", os.getenv("ADMIN_EMAIL", "admin@samilink.sa"))]

# =========================
# تسجيل الأخطاء
# =========================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name} :: {message}", "style": "{"},
        "simple": {"format": "[{levelname}] {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# =========================
# مدققات كلمات المرور
# =========================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =========================
# الجلسات
# =========================
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 7)  # أسبوع
SESSION_SAVE_EVERY_REQUEST = env_bool("SESSION_SAVE_EVERY_REQUEST", False)

# =========================
# مصادقة وتوجيه
# =========================
LOGIN_URL = os.getenv("LOGIN_URL", "accounts:login")
LOGIN_REDIRECT_URL = os.getenv("LOGIN_REDIRECT_URL", "website:home")
LOGOUT_REDIRECT_URL = os.getenv("LOGOUT_REDIRECT_URL", "website:home")

# =========================
# DRF
# =========================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": env_int("DRF_PAGE_SIZE", 25),
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        *(
            ["rest_framework.renderers.BrowsableAPIRenderer"]
            if DEBUG
            else []
        ),
    ],
}

# =========================
# CORS (اختياري)
# =========================
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOW_CREDENTIALS = env_bool("CORS_ALLOW_CREDENTIALS", True)

# =========================
# Cloudinary Storage
# =========================
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME', 'dnob4uzo6'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY', '323685142587988'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET', 't1J7Pfi-7Rh1i6n-DftrxuP5Kg8'),
}

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# =========================
# إعدادات نهائية
# =========================
APPEND_SLASH = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
