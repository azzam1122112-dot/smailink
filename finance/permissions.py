from __future__ import annotations

from typing import Iterable, Optional

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


# =========================================================
# إعدادات عامة للأدوار/المجموعات/الأذونات المرتبطة بالمالية
# عدّل القوائم أدناه إذا استخدمت تسميات مختلفة في مشروعك.
# =========================================================

# أدوار نصية في حقل user.role (إن وُجد)
FINANCE_ROLES = {"finance", "manager", "admin", "supervisor"}  # اتركها واسعة قليلًا

# أسماء مجموعات يمكن إضافتها عبر لوحة المشرف
FINANCE_GROUPS = {"finance", "financial", "accounting", "managers"}

# أكواد أذونات (permissions) إن كنت تستخدم نظام صلاحيات دقيق
# مثال: أنشئ صلاحية مخصصة "finance_access" على أي موديل لديك.
FINANCE_PERMS = {
    "finance_access",
    "finance.view_invoice",
    "finance.change_invoice",
    "finance.view_financesettings",
    "finance.change_financesettings",
}


# =========================================================
# أدوات داخلية
# =========================================================
def _safe_str(val: object) -> str:
    try:
        return (val or "").strip().lower()
    except Exception:
        return ""


def _reverse_or_home(*names: str) -> str:
    """
    يحاول عمل reverse لأسماء متعددة؛ يسقط إلى "/" عند الفشل لتجنب NoReverseMatch.
    """
    for n in names:
        try:
            return reverse(n)
        except NoReverseMatch:
            continue
        except Exception:
            continue
    return "/"


def in_groups(user, groups: Iterable[str]) -> bool:
    """
    هل المستخدم ضمن أي مجموعة من المجموعات المعطاة؟
    آمن حتى لو لم تكن المجموعات موجودة.
    """
    if not user or isinstance(user, AnonymousUser):
        return False
    try:
        target = {g.strip().lower() for g in groups if g and g.strip()}
        if not target:
            return False
        user_groups = set(user.groups.values_list("name", flat=True))
        user_groups = {g.strip().lower() for g in user_groups}
        return bool(target & user_groups)
    except Exception:
        return False


def has_any_perm(user, perms: Iterable[str]) -> bool:
    """
    يتحقق إن كان يملك أي إذن من القائمة (باستخدام نظام صلاحيات Django).
    """
    if not user or isinstance(user, AnonymousUser):
        return False
    try:
        for p in perms:
            code = _safe_str(p)
            if not code:
                continue
            # صيغ محتملة: "app_label.codename" أو "codename" فقط
            if "." in code:
                if user.has_perm(code):
                    return True
            else:
                # ابحث عن أي إذن ينتهي بنفس الكود نادرًا — أو استخدم has_perms مع app_label إذا كان معروفًا
                # لتجنب تبعيات على app_label، نحاول فحص كل أذونات المستخدم محليًا
                if Permission.objects.filter(codename=code, user=user).exists():
                    return True
                if user.is_superuser:
                    return True
        return False
    except Exception:
        return False


# =========================================================
# فاحصو الصلاحيات الأساسية
# =========================================================
def is_finance(user) -> bool:
    """
    قاعدة موحّدة:
    - superuser/staff = مسموح.
    - role ضمن FINANCE_ROLES = مسموح.
    - في مجموعة ضمن FINANCE_GROUPS = مسموح.
    - لديه أي من FINANCE_PERMS = مسموح.
    """
    if not user or isinstance(user, AnonymousUser):
        return False

    # أولوية واضحة
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    # role النصي
    role = _safe_str(getattr(user, "role", ""))
    if role and role in FINANCE_ROLES:
        return True

    # المجموعات
    if in_groups(user, FINANCE_GROUPS):
        return True

    # الأذونات الدقيقة
    if has_any_perm(user, FINANCE_PERMS):
        return True

    return False


def is_manager_like(user) -> bool:
    """
    مدير/إداري واسع الصلاحيات (قد يفيد لعرض روابط إضافية).
    """
    if not user or isinstance(user, AnonymousUser):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    role = _safe_str(getattr(user, "role", ""))
    return role in {"manager", "admin", "supervisor"}


def has_any_role(user, roles: Iterable[str]) -> bool:
    """
    يتحقق من role نصي (lower) مقابل أي عنصر بالقائمة.
    """
    if not user or isinstance(user, AnonymousUser):
        return False
    role = _safe_str(getattr(user, "role", ""))
    target = { _safe_str(r) for r in roles if r }
    return bool(role and role in target)


# =========================================================
# Decorator للـ FBVs
# =========================================================
def finance_required(view_func=None, *, redirect_names: Optional[Iterable[str]] = None, message: str = ""):
    """
    استخدمه على دوال العرض:
        @login_required
        @finance_required
        def my_view(...):
            ...

    redirect_names: أسماء URL للمحاولة عند الرفض (يُستخدم أول valid أو "/").
    message: رسالة مخصّصة عند الرفض.
    """
    if redirect_names is None:
        redirect_names = ("finance:finance_home", "website:home", "home", "index")

    def _check(user) -> bool:
        return is_finance(user)

    def _decorator(fn):
        @user_passes_test(_check, login_url=_reverse_or_home(*redirect_names))
        def _wrapped(request: HttpRequest, *args, **kwargs):
            if not is_finance(getattr(request, "user", None)):
                if message:
                    messages.error(request, message)
                else:
                    messages.error(request, "غير مصرح بالوصول إلى هذه الصفحة (مالية).")
                return redirect(_reverse_or_home(*redirect_names))
            return fn(request, *args, **kwargs)

        return _wrapped

    return _decorator if view_func is None else _decorator(view_func)


# =========================================================
# Mixin للـ CBVs
# =========================================================
class FinanceRequiredMixin(UserPassesTestMixin):
    """
    أضِف هذا الـ Mixin لأي Class-Based View يتطلب صلاحيات مالية.
    مثال:
        class CollectionsView(FinanceRequiredMixin, ListView):
            template_name = "finance/collections_report.html"
            ...

    يمكن تخصيص رسالة الرفض ووجهة التحويل عبر خواص الصف.
    """
    permission_denied_message = "غير مصرح بالوصول إلى هذه الصفحة (مالية)."
    redirect_names: tuple[str, ...] = ("finance:finance_home", "website:home", "home", "index")

    def test_func(self) -> bool:
        user = getattr(self.request, "user", None)
        return is_finance(user)

    def handle_no_permission(self) -> HttpResponse:
        try:
            messages.error(self.request, self.permission_denied_message)
        except Exception:
            pass
        return redirect(_reverse_or_home(*self.redirect_names))


# =========================================================
# مُلحقات اختيارية لتحسين تجربة القالب/الكونتكست
# =========================================================
def attach_finance_flags(request: HttpRequest) -> None:
    """
    يضيف أعلامًا على request يمكن أن تُفيد في القوالب أو الفيوز.
    لا يفعل شيئًا إن لم تتوفر الخاصية.
    """
    try:
        user = getattr(request, "user", None)
        setattr(request, "is_finance", is_finance(user))
        setattr(request, "is_manager_like", is_manager_like(user))
    except Exception:
        # نتجاهل بصمت — لا نُعطّل الطلب
        pass


def finance_guard_or_redirect(request: HttpRequest, *, message: str = "", redirect_names: Optional[Iterable[str]] = None) -> Optional[HttpResponse]:
    """
    حارس بسيط للاستخدام داخل الفيوز:
        if (resp := finance_guard_or_redirect(request)):
            return resp
        # تابع منطق الصفحة…

    يرجع HttpResponse تحويل عند الرفض، أو None عند السماح.
    """
    if is_finance(getattr(request, "user", None)):
        return None

    if not redirect_names:
        redirect_names = ("finance:finance_home", "website:home", "home", "index")

    try:
        if message:
            messages.error(request, message)
        else:
            messages.error(request, "غير مصرح بعرض هذه الصفحة (مالية).")
    except Exception:
        pass

    return redirect(_reverse_or_home(*redirect_names))
