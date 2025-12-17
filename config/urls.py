# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url='/static/img/favicon.ico', permanent=True)),
    # لوحة الإدارة
    path("admin/", admin.site.urls),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),

    # تطبيقات ذات مسارات واضحة
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("marketplace/", include(("marketplace.urls", "marketplace"), namespace="marketplace")),
    path("finance/", include(("finance.urls", "finance"), namespace="finance")),
    path("disputes/", include(("disputes.urls", "disputes"), namespace="disputes")),
    path("uploads/", include(("uploads.urls", "uploads"), namespace="uploads")),
    path("employees/", include(("profiles.urls", "profiles"), namespace="profiles")),
    path("agreements/", include(("agreements.urls", "agreements"), namespace="agreements")),

    # إشعارات — استخدم المسار الموجود فعليًا في مشروعك
    path("notifications/", include(("notifications.urls", "notifications"), namespace="notifications")),

    # الجذور/المسارات العامة
    path("", include(("website.urls", "website"), namespace="website")),
    path("", include(("core.urls", "core"), namespace="core")),
]

# ملفات الوسائط أثناء التطوير
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
