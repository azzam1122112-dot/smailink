from __future__ import annotations
import logging
from typing import Any, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.contrib.contenttypes.models import ContentType

from .models import Notification

logger = logging.getLogger(__name__)

def _send_email_safely(subject: str, body: str, to_email: str | None) -> None:
    try:
        if getattr(settings, "DEFAULT_FROM_EMAIL", None) and to_email:
            send_mail(subject, body or "", settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=True)
    except Exception:
        logger.exception("notifications: failed to send email")

def create_notification(
    *,
    recipient,
    title: str,
    body: str = "",
    url: str = "",
    actor=None,
    target: Any | None = None,
    send_email: bool = False,
) -> Optional[Notification]:
    """
    ينشئ تنبيهًا للمستخدم مع ربط اختياري بـ target (GenericFK) + رابط اختياري.
    يرجع Notification عند النجاح أو None عند الفشل (لا يرمي استثناءات).
    """
    try:
        ct = None
        obj_id = None
        if target is not None:
            try:
                ct = ContentType.objects.get_for_model(target.__class__)
                obj_id = getattr(target, "pk", None)
            except Exception:
                ct = None
                obj_id = None

        n = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            title=title[:160],
            body=body or "",
            url=url or "",
            content_type=ct,
            object_id=obj_id,
        )

        if send_email:
            _send_email_safely(title, body, getattr(recipient, "email", None))

        return n
    except Exception:
        logger.exception("notifications: failed to create notification")
        return None
