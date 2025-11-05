# marketplace/views_offers.py
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.core.exceptions import FieldDoesNotExist
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
)
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.permissions import require_role  # ✅ كان مفقوداً
from .models import Request, Offer

logger = logging.getLogger(__name__)

# جرّب استيراد المُخطر من views، وإن فشل وفّر بديل صامت
try:
    from .views import _notify_offer_selected  # موجود عادةً في marketplace/views.py
except Exception:
    def _notify_offer_selected(off: Offer) -> None:
        # بديل صامت عند غياب الدالة لتجنّب NameError
        return


# =========================
# Helpers (RBAC / meta)
# =========================
def _is_admin(user) -> bool:
    """يعتبر المستخدم إدارياً إذا كان staff/superuser أو دوره admin/manager."""
    return bool(
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "role", "") in {"admin", "manager"}
    )

def _model_has_field(model_cls, field_name: str) -> bool:
    """تحقق آمن من وجود الحقل في الموديل قبل استخدامه في update_fields."""
    try:
        model_cls._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


# =========================
# عروض الموظفين
# =========================
@login_required
@require_POST
@transaction.atomic
def offer_create(request: HttpRequest, request_id: int) -> HttpResponse:
    """
    الموظف يرسل عرضًا على طلب جديد.

    الأمان والمنطق:
    - POST فقط (@require_POST).
    - ممنوع عندما الطلب مجمّد (نزاع).
    - يُسمح فقط للموظف أو للإدارة.
    - يمنع التكرار لنفس الموظف (إن وُجد عرض سابق معلّق/مختار).
    - يتوقع أن يكون الطلب في حالة NEW.
    - التحقق من السعر كـ Decimal موجبة، وتطبيع الملاحظات.
    """
    req = get_object_or_404(Request.objects.select_for_update(), pk=request_id)

    role = getattr(request.user, "role", "")
    if not (_is_admin(request.user) or role == "employee"):
        return HttpResponseForbidden("ليست لديك صلاحية لإرسال عرض على هذا الطلب.")

    if getattr(req, "is_frozen", False) or str(getattr(req, "status", "")).lower() == "disputed":
        messages.error(request, "لا يمكن إرسال عرض: الطلب في حالة نزاع.")
        return redirect("marketplace:request_detail", pk=req.pk)

    # لا عروض إلا على NEW وغير المسند
    if str(getattr(req, "status", "")).lower() != getattr(Request.Status, "NEW", "new"):
        messages.info(request, "لا يمكن إرسال عرض إلا على الطلبات الجديدة.")
        return redirect("marketplace:request_detail", pk=req.pk)

    if getattr(req, "assigned_employee_id", None):
        messages.info(request, "تم إسناد الطلب بالفعل.")
        return redirect("marketplace:request_detail", pk=req.pk)

    # منع تكرار عروض الموظف نفسه على نفس الطلب (pending/selected)
    if Offer.objects.filter(
        request=req,
        employee=request.user,
        status__in=[getattr(Offer.Status, "PENDING", "pending"),
                    getattr(Offer.Status, "SELECTED", "selected")],
    ).exists():
        messages.info(request, "لديك عرض سابق على هذا الطلب.")
        return redirect("marketplace:request_detail", pk=req.pk)

    raw_price = (request.POST.get("price") or "").strip()
    notes = (request.POST.get("notes") or "").strip()

    try:
        price = Decimal(raw_price)
        if price <= 0:
            raise InvalidOperation
        price = price.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        messages.error(request, "قيمة السعر غير صحيحة. يرجى إدخال رقم صالح أكبر من 0.")
        return redirect("marketplace:request_detail", pk=req.pk)

    Offer.objects.create(
        request=req,
        employee=request.user,
        price=price,
        notes=notes[:2000],  # حماية من مدخلات طويلة جدًا
        status=getattr(Offer.Status, "PENDING", "pending"),
    )
    messages.success(request, "تم إرسال العرض بنجاح.")
    return redirect("marketplace:request_detail", pk=req.pk)


@require_role("client")
@require_POST  # ✅ نفرض POST هنا أيضاً
@transaction.atomic
def offer_select(request, offer_id):
    """
    اختيار العرض من العميل (أو staff/admin عبر require_role).
    - يرفض بقية العروض.
    - يحدّث حالة العرض المختار.
    - يسند الطلب للموظف ويغيّر حالته إلى OFFER_SELECTED.
    - لا يلمس حقولاً غير موجودة (مثل offer_selected_at) إلا بعد التحقق.
    """
    off = get_object_or_404(
        Offer.objects.select_related("request").select_for_update(),
        pk=offer_id
    )
    req = off.request

    # السماح للعميل أو الإدارة فقط (الديكوريتر يسمح للستاف/الأدمِن)
    if req.client != request.user and not getattr(request.user, "is_staff", False):
        return HttpResponseForbidden("غير مسموح")

    # منع الاختيار أثناء النزاع
    if getattr(req, "is_frozen", False) or str(getattr(req, "status", "")).lower() == "disputed":
        messages.error(request, "لا يمكن اختيار عرض: الطلب في حالة نزاع.")
        return redirect("marketplace:request_detail", pk=req.pk)

    # صلاحية/وضع العرض
    if hasattr(off, "can_select") and not off.can_select(request.user):
        return HttpResponseForbidden("لا يمكن اختيار هذا العرض")
    if getattr(off, "status", None) != getattr(Offer.Status, "PENDING", "pending"):
        messages.info(request, "لا يمكن اختيار عرض غير معلّق.")
        return redirect("marketplace:request_detail", pk=req.pk)

    # ارفض بقية العروض
    Offer.objects.filter(request=req).exclude(pk=off.pk).update(
        status=getattr(Offer.Status, "REJECTED", "rejected")
    )

    # اختر هذا العرض (بدون selected_at إن لم يوجد)
    off.status = getattr(Offer.Status, "SELECTED", "selected")
    off.save(update_fields=["status"])  # لا تمرّر selected_at إن لم يوجد

    # إسناد الطلب وتحديث حالته
    req.assigned_employee = off.employee
    req.status = getattr(Request.Status, "OFFER_SELECTED", "offer_selected")

    request_update_fields = ["assigned_employee", "status"]

    # أضف offer_selected_at فقط إذا كان الحقل موجوداً
    if _model_has_field(Request, "offer_selected_at"):
        req.offer_selected_at = timezone.now()
        request_update_fields.append("offer_selected_at")

    if _model_has_field(Request, "updated_at"):
        req.updated_at = timezone.now()
        request_update_fields.append("updated_at")

    req.save(update_fields=request_update_fields)

    try:
        _notify_offer_selected(off)
    except Exception:
        pass

    messages.success(request, "تم اختيار العرض وإسناد الطلب")
    return redirect("marketplace:request_detail", pk=req.pk)


@login_required
@require_POST
@transaction.atomic
def offer_reject(request: HttpRequest, offer_id: int) -> HttpResponse:
    """
    رفض عرض من قِبل العميل (أو الإدارة).
    - POST فقط.
    - لا يؤثر على العروض الأخرى.
    - لا رفض أثناء حالة النزاع.
    """
    off = get_object_or_404(
        Offer.objects.select_related("request").select_for_update(),
        pk=offer_id
    )
    req = Request.objects.select_for_update().get(pk=off.request_id)

    is_client = (request.user == req.client)
    if not (is_client or _is_admin(request.user)):
        return HttpResponseForbidden("ليست لديك صلاحية لرفض العرض.")

    if getattr(req, "is_frozen", False) or str(getattr(req, "status", "")).lower() == "disputed":
        messages.error(request, "لا يمكن رفض عرض: الطلب في حالة نزاع.")
        return redirect("marketplace:request_detail", pk=req.pk)

    if off.status != getattr(Offer.Status, "PENDING", "pending"):
        messages.info(request, "لا يمكن رفض هذا العرض في حالته الحالية.")
        return redirect("marketplace:request_detail", pk=req.pk)

    off.status = getattr(Offer.Status, "REJECTED", "rejected")
    update_fields = ["status"]

    if _model_has_field(Offer, "updated_at"):
        off.updated_at = timezone.now()
        update_fields.append("updated_at")

    off.save(update_fields=update_fields)

    messages.success(request, "تم رفض العرض.")
    return redirect("marketplace:request_detail", pk=req.pk)
