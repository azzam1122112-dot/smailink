# marketplace/permissions.py
from __future__ import annotations

from typing import Protocol, Optional, Any


# ========= Typing Protocols (لا تعتمد على موديلات Django مباشرة) =========
class SupportsUser(Protocol):
    id: Optional[int]
    is_authenticated: bool
    is_staff: bool

    # قد تكون لديك خصائص إضافية على المستخدم
    # نتعامل معها عبر getattr لتفادي الأخطاء إن لم تكن موجودة.
    # role: "admin" | "manager" | "gm" | "finance" | "employee" | "client"
    # is_manager / is_admin / is_employee ... إلخ.


class SupportsOffersManager(Protocol):
    """الـ RelatedManager لحقل offers على الطلب."""
    # في Django الحديث: .model — في القديم ربما .rel.model
    @property
    def model(self) -> Any: ...
    def filter(self, *args, **kwargs): ...
    def exists(self) -> bool: ...


class SupportsRequest(Protocol):
    id: int
    client_id: int
    assigned_employee_id: Optional[int]

    # بعض المشاريع تسميها status وأخرى state
    status: Any  # قد يكون Enum أو نص
    # اختياريًا
    state: Any

    # علاقات اختيارية:
    offers: SupportsOffersManager
    selected_offer: Optional[Any]


# ========= Helpers =========
def _role(user: SupportsUser) -> str:
    return (getattr(user, "role", "") or "").lower()


def _is_managerial(user: SupportsUser) -> bool:
    """إدارة/طاقم: admin/manager/gm/finance أو staff/superuser."""
    role = _role(user)
    return bool(
        user.is_authenticated
        and (
            user.is_staff
            or getattr(user, "is_superuser", False)
            or getattr(user, "is_admin", False)
            or role in {"admin", "manager", "gm", "finance"}
        )
    )


def _status_str(val: Any) -> str:
    """يحوّل قيمة الحالة (Enum أو نص) إلى lower string آمن."""
    if val is None:
        return ""
    try:
        # Enum: Request.Status.NEW -> ".value" غالبًا نص
        return str(getattr(val, "value", val)).strip().lower()
    except Exception:
        return str(val).strip().lower()


def _req_status(req: SupportsRequest) -> str:
    s = _status_str(getattr(req, "status", None))
    return s or _status_str(getattr(req, "state", None))


# ========= Basic checks =========
def is_staff_or_manager(user: SupportsUser) -> bool:
    return _is_managerial(user)


def is_client(user: SupportsUser, request_obj: SupportsRequest) -> bool:
    return bool(user.is_authenticated and request_obj.client_id == getattr(user, "id", None))


def is_assigned_employee(user: SupportsUser, request_obj: SupportsRequest) -> bool:
    return bool(
        user.is_authenticated
        and getattr(request_obj, "assigned_employee_id", None) == getattr(user, "id", None)
    )


def has_employee_offer(user: SupportsUser, request_obj: SupportsRequest) -> bool:
    """
    يتحقق إن كان للموظف عرض على هذا الطلب.
    يدعم كلا الحالتين:
    - request.offers.model
    - request.offers.rel.model (قديم)
    """
    if not user.is_authenticated or not hasattr(request_obj, "offers"):
        return False

    offers_mgr = request_obj.offers
    offer_model = getattr(offers_mgr, "model", None) or getattr(getattr(offers_mgr, "rel", None), "model", None)
    if not offer_model:
        return False

    employee_field = "employee"
    # في حال كان لديك created_by أو مشابه بدلاً من employee
    if not hasattr(offer_model, employee_field):
        employee_field = "created_by"

    try:
        return offer_model.objects.filter(request=request_obj, **{employee_field: user}).exists()
    except Exception:
        return False


# ========= High-level permissions =========
def can_view_request(user: SupportsUser, request_obj: SupportsRequest) -> bool:
    """
    سياسة عرض تفاصيل الطلب:
    1) الإدارة/الطاقم: مسموح دائمًا.
    2) العميل المالك: مسموح.
    3) الموظف المُسنَّد: مسموح.
    4) الموظفون يمكنهم فتح طلب NEW وغير مُسنَّد لتقديم عرض.
    5) الموظف صاحب العرض المختار (selected_offer) يمكنه العرض.
    """
    if is_staff_or_manager(user):
        return True
    if is_client(user, request_obj):
        return True
    if is_assigned_employee(user, request_obj):
        return True

    role = _role(user)
    status_lc = _req_status(request_obj)
    if role == "employee":
        # جديد وغير مُسنّد → افتح التفاصيل لتقديم العرض
        if status_lc == "new" and getattr(request_obj, "assigned_employee_id", None) is None:
            return True

        # صاحب العرض المختار (إن وُجد selected_offer)
        selected = getattr(request_obj, "selected_offer", None)
        if selected and getattr(selected, "employee_id", None) == getattr(user, "id", None):
            return True

        # بديل محافظ: إن كان لديه عرض سابق (للإطلاع والمتابعة)
        if has_employee_offer(user, request_obj):
            return True

    return False


def can_see_client_contacts(user: SupportsUser, request_obj: SupportsRequest) -> bool:
    """
    تُكشف بيانات العميل فقط للمالك، أو الإدارة/الطاقم، أو الموظف المُسنَّد،
    أو الموظف الذي تم اختيار عرضه (selected_offer).
    """
    if is_staff_or_manager(user) or is_client(user, request_obj) or is_assigned_employee(user, request_obj):
        return True

    selected = getattr(request_obj, "selected_offer", None)
    if selected and getattr(selected, "employee_id", None) == getattr(user, "id", None):
        return True

    return False


__all__ = [
    "is_staff_or_manager",
    "is_client",
    "is_assigned_employee",
    "has_employee_offer",
    "can_view_request",
    "can_see_client_contacts",
]
