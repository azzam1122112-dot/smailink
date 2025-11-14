# disputes/signals.py
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from disputes.models import Dispute
from marketplace.models import Request

# إشعارات (اختياري): نستدعيها بأمان إن وُجدت
try:
    from notifications.utils import create_notification as _notify
except Exception:  # pragma: no cover
    _notify = None  # type: ignore

logger = logging.getLogger(__name__)


# =========================
# أدوات مساعدة للتجميد/الفك
# =========================
def _freeze_request(req: Request, reason: str = "dispute_opened") -> None:
    """
    يجمّد الطلب آمنًا:
    - يضبط الحالة إلى DISPUTED (إن وُجد Enum)،
    - is_frozen=True،
    - ويحاول استدعاء req.freeze() إن كانت متاحة للحفاظ على منطقك الداخلي.
    """
    try:
        with transaction.atomic():
            # دعوة الدالة المخصّصة إن وجدت
            if hasattr(req, "freeze") and callable(getattr(req, "freeze")):
                req.freeze()  # يتولى هو الحقول
                return

            # fallback: تحديث الحقول يدويًا
            new_status = getattr(getattr(Request, "Status", None), "DISPUTED", "disputed")
            updates = []
            if hasattr(req, "status"):
                if getattr(req, "status") != new_status:
                    setattr(req, "status", new_status)
                    updates.append("status")

            if hasattr(req, "is_frozen"):
                if not getattr(req, "is_frozen", False):
                    setattr(req, "is_frozen", True)
                    updates.append("is_frozen")

            if hasattr(req, "freeze_reason"):
                setattr(req, "freeze_reason", reason)
                updates.append("freeze_reason")

            if hasattr(req, "updated_at"):
                from django.utils import timezone

                req.updated_at = timezone.now()
                updates.append("updated_at")

            if updates:
                req.save(update_fields=list(dict.fromkeys(updates)))
    except Exception:
        logger.exception("فشل تجميد الطلب (request_id=%s)", getattr(req, "id", None))


def _unfreeze_request_if_no_open_disputes(req: Request) -> None:
    """
    يرفع التجميد إذا لم تبقَ نزاعات مفتوحة على الطلب.
    لا يغير الحالة إن كانت مكتملة/ملغاة؛ فقط يزيل is_frozen ويعيد freeze_reason للفارغ.
    """
    try:
        with transaction.atomic():
            # لو هناك أي نزاع مفتوح، لا نفك التجميد
            if Dispute.objects.filter(request_id=req.id, is_open=True).exists():
                return

            # دالة مخصّصة إن وجدت
            if hasattr(req, "unfreeze") and callable(getattr(req, "unfreeze")):
                req.unfreeze()
                return

            updates = []
            if hasattr(req, "is_frozen") and getattr(req, "is_frozen", False):
                req.is_frozen = False
                updates.append("is_frozen")

            if hasattr(req, "freeze_reason") and getattr(req, "freeze_reason", None):
                req.freeze_reason = ""
                updates.append("freeze_reason")

            if hasattr(req, "updated_at"):
                from django.utils import timezone

                req.updated_at = timezone.now()
                updates.append("updated_at")

            if updates:
                req.save(update_fields=list(dict.fromkeys(updates)))
    except Exception:
        logger.exception("فشل رفع تجميد الطلب (request_id=%s)", getattr(req, "id", None))


def _safe_notify(user, title: str, body: str = "", url: str = "") -> None:
    """إرسال إشعار/بريد بشكل آمن إن كانت البنية متاحة."""
    if not user:
        return
    try:
        if _notify:
            _notify(recipient=user, title=title, body=body, url=url)
    except Exception:  # pragma: no cover
        # لا نكسر التدفق بسبب إشعار
        logger.debug("تعذر إرسال إشعار: %s", title)


# =====================================
# تتبع تغيّر is_open (pre_save + post_save)
# =====================================
@receiver(pre_save, sender=Dispute, dispatch_uid="dispute_presave_capture_old_is_open")
def _capture_old_is_open(sender, instance: Dispute, **kwargs):
    """
    قبل الحفظ: خزّن القيمة القديمة لـ is_open على الـ instance حتى نستطيع معرفة الانتقال.
    """
    if instance.pk:
        try:
            old = Dispute.objects.only("is_open").get(pk=instance.pk)
            # نعلّقها على الـ instance للاستهلاك بعد الحفظ
            setattr(instance, "_old_is_open", bool(old.is_open))
        except Dispute.DoesNotExist:
            setattr(instance, "_old_is_open", None)
    else:
        setattr(instance, "_old_is_open", None)


@receiver(post_save, sender=Dispute, dispatch_uid="dispute_postsave_freeze_unfreeze")
def on_dispute_saved(sender, instance: Dispute, created: bool, **kwargs):
    """
    - عند الإنشاء المفتوح: جمّد الطلب فورًا.
    - عند التعديل: إن تغيّرت is_open من False→True نجمّد؛ ومن True→False نرفع التجميد (إن لم تبق نزاعات مفتوحة).
    - نرسل إشعارات للطرفين + المالية/الإدارة (اختياري).
    """
    req: Optional[Request] = getattr(instance, "request", None)
    if not req:
        return

    try:
        was_open = getattr(instance, "_old_is_open", None)
        is_open = bool(getattr(instance, "is_open", False))

        if created:
            if is_open:
                _freeze_request(req, reason="dispute_opened")
                _notify_parties_on_open(instance)
        else:
            # انتقال الحالة
            if was_open is True and is_open is False:
                _unfreeze_request_if_no_open_disputes(req)
                _notify_parties_on_close(instance)
            elif (was_open is False or was_open is None) and is_open is True:
                _freeze_request(req, reason="dispute_reopened")
                _notify_parties_on_open(instance)

    except Exception:
        logger.exception(
            "فشل منطق ما بعد حفظ النزاع (dispute_id=%s, request_id=%s)",
            getattr(instance, "id", None),
            getattr(req, "id", None),
        )


@receiver(post_delete, sender=Dispute, dispatch_uid="dispute_postdelete_unfreeze_if_needed")
def on_dispute_deleted(sender, instance: Dispute, **kwargs):
    """
    عند حذف النزاع: إن لم تبقَ نزاعات مفتوحة على الطلب، نرفع التجميد.
    """
    req: Optional[Request] = getattr(instance, "request", None)
    if not req:
        return
    try:
        _unfreeze_request_if_no_open_disputes(req)
    except Exception:
        logger.exception(
            "فشل معالجة ما بعد حذف النزاع (dispute_id=%s, request_id=%s)",
            getattr(instance, "id", None),
            getattr(req, "id", None),
        )


# ===========================
# إشعارات (اختيارية ولطيفة)
# ===========================
def _notify_parties_on_open(dispute: Dispute) -> None:
    """إشعار العميل والموظف والمالية/الإدارة عند فتح نزاع."""
    if not _notify:
        return
    try:
        req: Request = dispute.request
        url = ""
        try:
            from django.urls import reverse

            url = reverse("marketplace:request_detail", args=[req.pk])
        except Exception:
            url = ""
        # العميل
        _safe_notify(getattr(req, "client", None), "تم فتح نزاع على طلبك", f"رقم الطلب #{req.pk}.", url)
        # الموظف
        _safe_notify(getattr(req, "assigned_employee", None), "تم فتح نزاع على طلب مُسند لك", f"رقم الطلب #{req.pk}.", url)
        # المالية (إن وُجدت مجموعة/دور)
        finance_user = getattr(getattr(settings, "FINANCE_CONTACT", None), "user", None)
        if finance_user:
            _safe_notify(finance_user, "إشعار مالي: نزاع جديد", f"طلب #{req.pk} تحت النزاع.", url)
    except Exception:
        logger.debug("تعذر إرسال إشعارات فتح النزاع", exc_info=True)


def _notify_parties_on_close(dispute: Dispute) -> None:
    """إشعار الأطراف عند إغلاق النزاع."""
    if not _notify:
        return
    try:
        req: Request = dispute.request
        url = ""
        try:
            from django.urls import reverse

            url = reverse("marketplace:request_detail", args=[req.pk])
        except Exception:
            url = ""
        _safe_notify(getattr(req, "client", None), "تم إغلاق النزاع", f"رقم الطلب #{req.pk}.", url)
        _safe_notify(getattr(req, "assigned_employee", None), "تم إغلاق نزاع على طلب مُسند لك", f"رقم الطلب #{req.pk}.", url)
    except Exception:
        logger.debug("تعذر إرسال إشعارات إغلاق النزاع", exc_info=True)
