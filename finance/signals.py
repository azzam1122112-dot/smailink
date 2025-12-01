# finance/signals.py
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import post_migrate, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import FinanceSettings, Invoice
from .utils import invalidate_finance_cfg_cache

logger = logging.getLogger(__name__)

# هل تريد أن يتم إكمال الطلب تلقائيًا بعد دفع الفواتير واعتماد المراحل؟
FIN_AUTOCOMPLETE = getattr(settings, "FINANCE_AUTOCOMPLETE_ON_PAID", True)

# عدد أيام الأمان قبل أن يصبح أمر الصرف جاهزًا للصرف الفعلي
PAYOUT_SAFETY_DAYS = getattr(settings, "PAYOUT_SAFETY_DAYS", 3)


@receiver(post_save, sender=FinanceSettings)
def finance_settings_saved(sender, instance: FinanceSettings, **kwargs):
    """
    عند حفظ إعدادات المالية نقوم بتفريغ الكاش.
    """
    try:
        invalidate_finance_cfg_cache()
    except Exception:
        logger.exception("failed to invalidate finance cache after FinanceSettings save")


@receiver(post_migrate)
def ensure_finance_settings_exists(sender, **kwargs):
    """
    ضمان وجود FinanceSettings singleton بعد المايجريشن.
    """
    try:
        app_label = getattr(sender, "name", "") or ""
        if app_label.split(".")[-1] != "finance":
            return
        FinanceSettings.get_solo()
    except Exception:
        logger.exception("failed to ensure FinanceSettings singleton on post_migrate")


def _status_value(model_cls, name: str, fallback: str) -> str:
    """
    يرجع قيمة حالة من enum Status إن وُجد، وإلا يرجع fallback.
    """
    Status = getattr(model_cls, "Status", None)
    return getattr(Status, name, fallback) if Status else fallback


def _is_writable(obj, field: str) -> bool:
    """
    يتأكد أن الحقل قابل للكتابة (ليس property).
    """
    if not hasattr(obj, field):
        return False
    attr = getattr(type(obj), field, None)
    return not isinstance(attr, property)


def _get_req_status(req) -> str:
    """
    يرجع حالة الطلب كسلسلة lower من status أو state.
    """
    val = getattr(req, "status", None)
    if val is None and hasattr(req, "state"):
        val = getattr(req, "state", "")
    return (str(val or "")).strip().lower()


def _set_req_status(req, new_val: str) -> None:
    """
    يضبط حالة الطلب في status أو state.
    """
    if hasattr(req, "status") and _is_writable(req, "status"):
        req.status = new_val
    elif hasattr(req, "state") and _is_writable(req, "state"):
        req.state = new_val


def _all_positive_invoices_paid(agreement) -> bool:
    """
    يتحقق أن جميع الفواتير ذات المبلغ الإيجابي على الاتفاقية تم دفعها.
    """
    PAID_VAL = _status_value(Invoice, "PAID", "paid")
    invs = list(
        Invoice.objects.select_for_update()
        .filter(agreement_id=agreement.id)
        .only("id", "total_amount", "status")
    )
    for inv in invs:
        total = getattr(inv, "total_amount", None) or Decimal("0.00")
        if total <= 0:
            # الفواتير ذات القيمة <= 0 لا تُعتبر عائقًا
            continue
        if str(inv.status).lower() != str(PAID_VAL).lower():
            return False
    return True


def _all_milestones_client_approved(agreement) -> bool:
    """
    يتحقق أن جميع المراحل الخاصة بالاتفاقية تم اعتمادها من العميل.
    يدعم أكثر من مخطط محتمل (is_approved / approved_at / status).
    """
    try:
        Milestone = apps.get_model("agreements", "Milestone")
    except Exception:
        # لو لم يوجد موديل المراحل نعتبر الشرط متحققًا
        return True

    qs = Milestone.objects.filter(agreement_id=agreement.id)
    if not qs.exists():
        # لا توجد مراحل -> لا مانع
        return True

    if hasattr(Milestone, "is_approved"):
        return not qs.filter(is_approved=False).exists()

    if hasattr(Milestone, "approved_at"):
        return not qs.filter(approved_at__isnull=True).exists()

    if hasattr(Milestone, "status"):
        approved_val = _status_value(Milestone, "APPROVED", "approved")
        return not qs.exclude(status=approved_val).exists()

    # في حالة عدم القدرة على التحقق نفضّل عدم الإكمال التلقائي
    return False


def _try_set_request_in_progress(req) -> None:
    """
    يجعل الطلب قيد التنفيذ IN_PROGRESS عند دفع أي فاتورة، ما لم يكن في حالة نهائية.
    """
    inprog_val = _status_value(type(req), "IN_PROGRESS", "in_progress")

    # لو عندك دالة رسمية للانتقال بعد الدفع
    if hasattr(req, "mark_paid_and_start"):
        try:
            req.mark_paid_and_start()
            return
        except ValidationError:
            return
        except Exception:
            logger.exception("mark_paid_and_start failed for request %s", getattr(req, "pk", None))

    current = _get_req_status(req)
    final_states = {
        _status_value(type(req), "COMPLETED", "completed"),
        _status_value(type(req), "CANCELLED", "cancelled"),
        _status_value(type(req), "DISPUTED", "disputed"),
    }
    if current in final_states:
        return

    _set_req_status(req, inprog_val)
    fields: list[str] = []
    if hasattr(req, "status"):
        fields.append("status")
    if hasattr(req, "state"):
        fields.append("state")
    if hasattr(req, "updated_at") and _is_writable(req, "updated_at"):
        req.updated_at = timezone.now()
        fields.append("updated_at")
    if fields:
        req.save(update_fields=fields)


def _try_set_request_completed(req) -> None:
    """
    يجعل حالة الطلب مكتملة COMPLETED، مع تعبئة completed_at و updated_at إن أمكن.
    """
    COMPLETED = _status_value(type(req), "COMPLETED", "completed")
    DISPUTED = _status_value(type(req), "DISPUTED", "disputed")
    CANCELLED = _status_value(type(req), "CANCELLED", "cancelled")

    cur = _get_req_status(req)
    if cur in {COMPLETED, DISPUTED, CANCELLED}:
        return

    if hasattr(req, "mark_completed"):
        try:
            req.mark_completed()
            return
        except ValidationError:
            return
        except Exception:
            logger.exception("mark_completed failed for request %s", getattr(req, "pk", None))

    _set_req_status(req, COMPLETED)
    fields: list[str] = []
    now = timezone.now()
    if hasattr(req, "status"):
        fields.append("status")
    if hasattr(req, "state"):
        fields.append("state")
    if hasattr(req, "completed_at") and _is_writable(req, "completed_at"):
        # لا نغيّر completed_at إن كانت مضبوطة مسبقًا
        if getattr(req, "completed_at", None) is None:
            req.completed_at = now
        fields.append("completed_at")
    if hasattr(req, "updated_at") and _is_writable(req, "updated_at"):
        req.updated_at = now
        fields.append("updated_at")
    if fields:
        req.save(update_fields=fields)


def _compute_completed_at(req) -> timezone.datetime:
    """
    يحاول استنتاج وقت اكتمال الطلب من الحقول المتاحة.
    يستخدم completed_at إن وجد، ثم closed_at/finished_at، ثم updated_at كملاذ أخير.
    """
    val = getattr(req, "completed_at", None)
    if val:
        return val
    for name in ("closed_at", "finished_at", "updated_at"):
        v = getattr(req, name, None)
        if v:
            return v
    return timezone.now()


def _get_payout_model():
    """
    يجلب موديل Payout من تطبيق finance بطريقة آمنة ضد الدوائر.
    """
    try:
        return apps.get_model("finance", "Payout")
    except Exception:
        logger.exception("failed to get Payout model")
        return None


def _compute_employee_payout_amount(agreement) -> Decimal | None:
    """
    يحسب صافي الموظف المتوقّع من الاتفاقية بالاعتماد على خدمة التسعير الرسمية.
    """
    try:
        from finance.services.pricing import breakdown_for_agreement, expected_tech_payout_on_complete
    except Exception:
        logger.exception("failed to import pricing services for payout computation")
        return None

    try:
        bd = breakdown_for_agreement(agreement)
        amount = expected_tech_payout_on_complete(bd)
        if amount is None:
            return None
        if amount <= Decimal("0.00"):
            return None
        return amount
    except Exception:
        logger.exception("failed to compute employee payout amount for agreement %s", getattr(agreement, "pk", None))
        return None


def _auto_create_employee_payout(agreement, req, invoice: Invoice) -> None:
    """
    ينشئ أمر صرف للموظف تلقائيًا بعد:
      - اكتمال الطلب،
      - دفع جميع الفواتير الإيجابية،
      - اعتماد جميع المراحل من العميل.

    أمر الصرف يكون بحالة PENDING (قيد المعالجة/مبلغ محجوز)،
    ويُترك قرار جاهزية الصرف للواجهة (بعد ٣ أيام من completed_at).
    """
    Payout = _get_payout_model()
    if Payout is None:
        return

    employee = getattr(agreement, "employee", None) or getattr(agreement, "assigned_employee", None)
    if not employee:
        # لا يمكن إنشاء أمر صرف بدون موظف واضح
        logger.warning(
            "skip auto payout: agreement %s has no employee attached",
            getattr(agreement, "pk", None),
        )
        return

    # منع التكرار: لو يوجد أمر صرف غير ملغي لنفس الاتفاقية نتوقف
    CANCELLED = _status_value(Payout, "CANCELLED", "cancelled")
    existing = (
        Payout.objects.select_for_update()
        .filter(agreement_id=agreement.id)
        .exclude(status=CANCELLED)
        .first()
    )
    if existing:
        # يوجد أمر صرف سابق (قيد المعالجة/جاهز/مدفوع...) -> لا ننشئ جديدًا
        return

    amount = _compute_employee_payout_amount(agreement)
    if amount is None:
        # فشل في حساب صافي الموظف -> لا ننشئ أمر صرف تلقائي
        return

    # حساب وقت اكتمال الطلب + أيام الأمان
    completed_at = _compute_completed_at(req)
    safety_days = int(PAYOUT_SAFETY_DAYS or 0)
    ready_at = completed_at + timedelta(days=safety_days)

    PENDING = _status_value(Payout, "PENDING", "pending")

    try:
        payout_fields: dict[str, object] = {
            "employee": employee,
            "agreement": agreement,
            "amount": amount,
            "status": PENDING,
            # ملاحظة: نفترض أن حجز المبلغ يتحقق بمجرد إنشاء الـ Payout بحالة PENDING.
            "note": (
                f"إنشاء تلقائي لأمر صرف بعد اكتمال الطلب #{getattr(req, 'pk', None)} "
                f"ودفع الفواتير واعتماد المراحل. جاهز للصرف بعد {safety_days} أيام من اكتمال المشروع."
            ),
        }

        # لو كان موديل Payout يحتوي على ready_at نستخدمه
        if hasattr(Payout, "ready_at"):
            payout_fields["ready_at"] = ready_at

        # لو كان يحتوي على invoice foreign key نربطه بالفاتورة الحالية
        if hasattr(Payout, "invoice"):
            payout_fields["invoice"] = invoice

        payout = Payout.objects.create(**payout_fields)

        logger.info(
            "auto-created payout id=%s for agreement=%s employee=%s amount=%s ready_at=%s",
            getattr(payout, "pk", None),
            getattr(agreement, "pk", None),
            getattr(employee, "pk", None),
            amount,
            ready_at,
        )
    except Exception:
        logger.exception(
            "failed to auto-create employee payout for agreement %s", getattr(agreement, "pk", None)
        )


@receiver(pre_save, sender=Invoice)
def _invoice_pre_save_track_status(sender, instance: Invoice, **kwargs):
    """
    قبل حفظ الفاتورة نقوم بتخزين الحالة القديمة على الكائن نفسه للتمييز بين التحديثات.
    """
    try:
        instance.__old_status = None
        if instance.pk:
            old = sender.objects.only("status").filter(pk=instance.pk).first()
            if old:
                instance.__old_status = old.status
    except Exception:
        logger.exception("failed to snapshot previous invoice status (id=%s)", getattr(instance, "pk", None))


@receiver(post_save, sender=Invoice)
def _invoice_post_save_sync_request(sender, instance: Invoice, created: bool, **kwargs):
    """
    بعد حفظ الفاتورة:
      - عند الانتقال إلى حالة PAID:
        1) نجعل الطلب IN_PROGRESS إن لم يكن نهائيًا.
        2) لو FIN_AUTOCOMPLETE مفعّل:
           - نتحقق أن جميع الفواتير الإيجابية مدفوعة.
           - نتحقق أن جميع المراحل معتمدة من العميل.
           - نكمل الطلب COMPLETED.
           - ننشئ أمر صرف تلقائي للموظف (Payout) بحالة PENDING وحجز للمبلغ.
    """
    try:
        PAID_VAL = _status_value(Invoice, "PAID", "paid")
        old_status = getattr(instance, "__old_status", None)
        new_status = getattr(instance, "status", None)

        # فقط عند transition إلى PAID
        if str(new_status).lower() != str(PAID_VAL).lower() or str(new_status).lower() == str(
            old_status or ""
        ).lower():
            return

        agreement = getattr(instance, "agreement", None)
        if not agreement:
            return

        req = getattr(agreement, "request", None)
        if not req:
            return

        with transaction.atomic():
            # 1) أي فاتورة تُدفع -> الطلب قيد التنفيذ
            _try_set_request_in_progress(req)

            if not FIN_AUTOCOMPLETE:
                # إن لم يكن الإكمال التلقائي مفعّلاً لا نواصل باقي المنطق
                return

            # 2) شرط الفواتير: جميع الفواتير الإيجابية على الاتفاقية مدفوعة
            if not _all_positive_invoices_paid(agreement):
                return

            # 3) شرط اعتماد المراحل من العميل
            if not _all_milestones_client_approved(agreement):
                return

            # 4) نكمّل الطلب
            _try_set_request_completed(req)

            # 5) إنشاء أمر صرف تلقائي للموظف (حجز مبلغ وصرف بعد ٣ أيام)
            _auto_create_employee_payout(agreement, req, instance)

    except Exception:
        logger.exception("failed to sync request and auto payout after invoice paid (invoice_id=%s)", getattr(instance, "pk", None))
