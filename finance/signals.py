# finance/signals.py
from __future__ import annotations

import logging
from typing import Optional

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_migrate, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import FinanceSettings, Invoice
from .utils import invalidate_finance_cfg_cache

logger = logging.getLogger(__name__)

# إعداد اختياري لتعطيل إكمال الطلب تلقائيًا عند السداد (مُفعّل افتراضيًا)
FIN_AUTOCOMPLETE = getattr(settings, "FINANCE_AUTOCOMPLETE_ON_PAID", True)


# =========================
# إعدادات المالية (Cache)
# =========================
@receiver(post_save, sender=FinanceSettings)
def finance_settings_saved(sender, instance: FinanceSettings, **kwargs):
    """
    عند حفظ الإعدادات المالية: امسح الكاش حتى تُقرأ القيم الجديدة فورًا.
    """
    try:
        invalidate_finance_cfg_cache()
    except Exception:
        logger.exception("failed to invalidate finance cache after FinanceSettings save")


@receiver(post_migrate)
def ensure_finance_settings_exists(sender, **kwargs):
    """
    بعد الهجرات: تأكّد من وجود سجل FinanceSettings (Singleton).
    """
    try:
        # نحصر التنفيذ على تطبيق finance فقط لتقليل الضجيج
        app_label = getattr(sender, "name", "") or ""
        if app_label.split(".")[-1] != "finance":
            return

        FinanceSettings.get_solo()  # سيُنشئه إن لم يوجد
    except Exception:
        logger.exception("failed to ensure FinanceSettings singleton on post_migrate")


# =====================================
# تتبّع تغيّر حالة الفاتورة إلى مدفوعة
# =====================================
def _request_status_value(model, name: str, fallback: str) -> str:
    """
    جلب قيمة الحالة من TextChoices إن وُجدت، وإلا إعادة fallback.
    """
    try:
        Status = getattr(model, "Status", None)
        return getattr(Status, name, fallback)
    except Exception:
        return fallback


def _is_writable(obj, field: str) -> bool:
    """تحقّق سريع أن الحقل قابل للكتابة وليس property."""
    if not hasattr(obj, field):
        return False
    attr = getattr(type(obj), field, None)
    from types import MappingProxyType  # defensive
    return not isinstance(attr, property)


@receiver(pre_save, sender=Invoice)
def _invoice_pre_save_track_status(sender, instance: Invoice, **kwargs):
    """
    قبل حفظ الفاتورة: خزّن الحالة السابقة لمقارنة التغيّر بعد الحفظ.
    """
    try:
        instance.__old_status = None
        if instance.pk:
            old = sender.objects.only("status").filter(pk=instance.pk).first()
            if old:
                instance.__old_status = old.status
    except Exception:
        logger.exception("failed to snapshot previous invoice status (id=%s)", getattr(instance, "id", None))


@receiver(post_save, sender=Invoice)
def _invoice_post_save_complete_request(sender, instance: Invoice, created: bool, **kwargs):
    """
    بعد حفظ الفاتورة: إن تغيّرت الحالة إلى (مدفوعة) نفّذ منطق إكمال الطلب/الاتفاقية
    في حال سُدِّدت **جميع الفواتير ذات الإجمالي > 0**.
    """
    if not FIN_AUTOCOMPLETE:
        return

    try:
        PAID_VAL = _request_status_value(Invoice, "PAID", "paid")
        old_status = getattr(instance, "__old_status", None)
        new_status = getattr(instance, "status", None)

        # لم تتغير إلى مدفوعة؟ لا شيء
        if new_status != PAID_VAL or new_status == old_status:
            return

        agreement = getattr(instance, "agreement", None)
        if agreement is None:
            return

        # سنحتاج للوصول إلى الطلب المرتبط
        req = getattr(agreement, "request", None)
        if req is None:
            return

        with transaction.atomic():
            # أعِد تحميل الفواتير من قاعدة البيانات للتأكّد النهائي
            invs = list(
                Invoice.objects.select_for_update()
                .filter(agreement_id=agreement.id)
                .only("id", "total_amount", "status")
            )

            # هل جميع الفواتير ذات إجمالي > 0 مدفوعة؟
            all_paid = True
            for inv in invs:
                try:
                    total = (inv.total_amount or 0)
                except Exception:
                    total = 0
                if total <= 0:
                    continue
                if inv.status != PAID_VAL:
                    all_paid = False
                    break

            if not all_paid:
                return

            # الطلب: تحقّق أن حالته تسمح بالإكمال
            Request = apps.get_model("marketplace", "Request")
            COMPLETED = _request_status_value(Request, "COMPLETED", "completed")
            DISPUTED = _request_status_value(Request, "DISPUTED", "disputed")
            CANCELLED = _request_status_value(Request, "CANCELLED", "cancelled")

            cur_status = (getattr(req, "status", "") or "").lower()
            if cur_status in {DISPUTED, CANCELLED, COMPLETED}:
                # لا نُغيّر إن كان مُكتمل أو مُلغى أو متنازع عليه
                return

            now = timezone.now()

            # وسم الطلب كمكتمل
            if _is_writable(req, "status"):
                req.status = COMPLETED
                fields = ["status"]
                if _is_writable(req, "completed_at"):
                    req.completed_at = now
                    fields.append("completed_at")
                if _is_writable(req, "updated_at"):
                    req.updated_at = now
                    fields.append("updated_at")
                req.save(update_fields=fields)

            # وسم الاتفاقية كمكتملة (بحذر عبر فحص الخيارات)
            Agreement = apps.get_model("agreements", "Agreement")
            AGREEMENT_COMPLETED = _request_status_value(Agreement, "COMPLETED", "completed")

            try:
                ag_status_field = agreement._meta.get_field("status")
                has_choices = bool(getattr(ag_status_field, "choices", ()))
                if not has_choices or AGREEMENT_COMPLETED in {c[0] for c in ag_status_field.choices}:
                    if _is_writable(agreement, "status"):
                        agreement.status = AGREEMENT_COMPLETED
                        ag_fields = ["status"]
                        if _is_writable(agreement, "updated_at"):
                            agreement.updated_at = now
                            ag_fields.append("updated_at")
                        agreement.save(update_fields=ag_fields)
            except Exception:
                # لو فشل فحص الحقل، لا نمنع إكمال الطلب
                logger.warning("agreement status completion skipped due to schema inspection issue (agreement_id=%s)", agreement.id)

    except Exception:
        logger.exception("failed to auto-complete request after invoice paid (invoice_id=%s)", getattr(instance, "id", None))
