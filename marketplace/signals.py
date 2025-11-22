# marketplace/signals.py
from __future__ import annotations
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import FieldDoesNotExist

from .models import Offer, Request

def _model_has_field(model_cls, field_name: str) -> bool:
    try:
        model_cls._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False

@receiver(post_save, sender=Offer)
def handle_offer_selection(sender, instance: Offer, created: bool, **kwargs):
    """
    عند تغيير حالة العرض إلى SELECTED:
    - نحدّث الطلب (الموظف المعيّن + الحالة).
    - لا نلمس حقولًا غير موجودة (offer_selected_at مثلاً) إلا بعد التحقق.
    ملاحظة: view يقوم أصلًا برفض بقية العروض وإسناد الطلب؛ هذه الإشارة تجعل السلوك متسقًا حتى لو تغيّر من الإدارة.
    """
    if created:
        return

    off = instance
    # نعمل فقط عند حالة SELECTED
    if getattr(off, "status", None) != getattr(Offer.Status, "SELECTED", "selected"):
        return

    req = off.request
    # حدث الطلب آمنًا
    req.assigned_employee = off.employee
    req.status = getattr(Request.Status, "OFFER_SELECTED", "offer_selected")

    update_fields = ["assigned_employee", "status"]

    if _model_has_field(Request, "offer_selected_at"):
        req.offer_selected_at = timezone.now()
        update_fields.append("offer_selected_at")

    if hasattr(req, "updated_at"):
        req.updated_at = timezone.now()
        update_fields.append("updated_at")

    # لا تمرّر حقول غير موجودة إطلاقًا
    req.save(update_fields=update_fields)

    # إشعار للعميل بوصول عرض جديد
    try:
        from notifications.utils import create_notification
        client = getattr(req, "client", None)
        if client:
            create_notification(
                recipient=client,
                title=f"تم اختيار عرض جديد لطلبك #{req.pk}",
                body=f"تم اختيار عرض الموظف {off.employee} لطلبك '{req.title}'. يمكنك مراجعة التفاصيل والموافقة على الاتفاقية.",
                url=req.get_absolute_url(),
                actor=off.employee,
                target=off,
            )
    except Exception:
        pass

    # إشعار للموظف عند اختيار عرضه
    try:
        from notifications.utils import create_notification
        employee = getattr(off, "employee", None)
        if employee:
            create_notification(
                recipient=employee,
                title=f"تم اختيار عرضك للطلب #{req.pk}",
                body=f"قام العميل {getattr(req, 'client', '')} باختيار عرضك للطلب '{req.title}'. يمكنك متابعة الاتفاقية والمشروع.",
                url=req.get_absolute_url(),
                actor=getattr(req, "client", None),
                target=off,
            )
    except Exception:
        pass
