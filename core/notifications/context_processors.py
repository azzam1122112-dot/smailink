# core/notifications/context_processors.py
from __future__ import annotations

from typing import Dict, Any

def notifications_context(request) -> Dict[str, Any]:
    """
    يمرّر عدد الإشعارات غير المقروءة + آخر 5 إشعارات للقوالب كلها.
    دفاعي: لو تطبيق notifications غير موجود ما يكسر الموقع.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "notifications_unread_count": 0,
            "notifications_latest": [],
            "notifications_url": "",
        }

    try:
        # عدّل المسار حسب اسم موديلك
        from notifications.models import Notification  # أو core.notifications.models
        from django.urls import reverse

        qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")

        unread_count = qs.filter(is_read=False).count()
        latest = list(qs[:5])

        return {
            "notifications_unread_count": unread_count,
            "notifications_latest": latest,
            "notifications_url": reverse("notifications:list"),
        }
    except Exception:
        return {
            "notifications_unread_count": 0,
            "notifications_latest": [],
            "notifications_url": "",
        }
