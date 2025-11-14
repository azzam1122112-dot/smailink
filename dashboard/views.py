# dashboard/views.py
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Value as V
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.dateparse import parse_date

logger = logging.getLogger(__name__)

# ====================== أمان وصلاحيات ======================

def _is_admin(user) -> bool:
    """تحقق دور المدير/المالية/السوبر (RBAC مبسّط)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return bool(getattr(user, "is_system_admin", False))


def _require_admin(request) -> bool:
    if not _is_admin(request.user):
        messages.error(request, "ليس لديك صلاحية الوصول لهذه الصفحة.")
        return False
    return True


# ====================== نماذج اختيارية (قد لا تتوفر) ======================

User = get_user_model()

try:
    from marketplace.models import Request, Offer  # type: ignore
except Exception:  # pragma: no cover
    Request = None  # type: ignore
    Offer = None    # type: ignore

try:
    from agreements.models import Agreement  # type: ignore
except Exception:  # pragma: no cover
    Agreement = None  # type: ignore

try:
    from finance.models import Invoice  # type: ignore
except Exception:  # pragma: no cover
    Invoice = None  # type: ignore

try:
    from disputes.models import Dispute  # type: ignore
except Exception:  # pragma: no cover
    Dispute = None  # type: ignore


# ====================== أدوات مساعدة عامة ======================

def _paginate(request, qs, per_page: int = 20):
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page") or 1
    return paginator.get_page(page_number)


def _safe_parse_date(value: str | None):
    if not value:
        return None
    try:
        return parse_date(value)
    except Exception:
        return None


def _daterange(request):
    """
    فلاتر زمنية موحّدة: ?from=YYYY-MM-DD&to=YYYY-MM-DD
    افتراضي: آخر 30 يومًا، مع تصحيح from<=to.
    """
    today = date.today()
    d_to = _safe_parse_date(request.GET.get("to")) or today
    d_from = _safe_parse_date(request.GET.get("from")) or (d_to - timedelta(days=30))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to


def _safe_reverse(name: str, **kwargs):
    """إرجاع رابط عكسي إن وُجد وإلا None بدون كسر القالب."""
    try:
        return reverse(name, kwargs=kwargs) if kwargs else reverse(name)
    except Exception:
        return None


def _money(value):
    return value if value is not None else Decimal("0.00")


def _model_has_field(model, field: str) -> bool:
    if not model:
        return False
    try:
        model._meta.get_field(field)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def _pick_field(model, candidates: list[str]) -> str | None:
    """اختر أول حقل موجود من القائمة."""
    for f in candidates:
        if _model_has_field(model, f):
            return f
    return None


def _only_fields(model, base: list[str]) -> list[str]:
    """أعد قائمة حقول موجودة فعليًا لاستخدامها مع .only()."""
    return [f for f in base if f and _model_has_field(model, f)]


# ====================== لوحة المدير (لوحة تشغيل) ======================

@login_required
def admin_dashboard(request):
    if not _require_admin(request):
        return redirect("website:home")

    # إلغاء التصفية الزمنية: عرض جميع البيانات بدون حدود زمنية
    d_from, d_to = None, None
    ctx = {
        "from": d_from,
        "to": d_to,
        "today": date.today(),  # ⬅️ متغيّر اليوم للقوالب
        "urls": {
            "users": _safe_reverse("accounts:user_list"),
            "requests": _safe_reverse("marketplace:request_list"),
            "invoices": _safe_reverse("finance:invoice_list"),
            "agreements": _safe_reverse("agreements:list"),
            "offers": _safe_reverse("marketplace:offers_list"),
            "disputes": _safe_reverse("disputes:list"),
        },
        "ops_alerts": [],
    }
    # حماية إضافية: تحويل أي متغير من نوع datetime إلى date في السياق
    from datetime import datetime, date as dt_date
    for k, v in ctx.items():
        if isinstance(v, datetime):
            ctx[k] = v.date()

    # ---- المستخدمون
    try:
        users_qs = User.objects.all().only(*_only_fields(User, ["id", "email", "name", "date_joined", "is_staff"]))
        ctx["users_total"] = users_qs.count()
        ctx["users_staff"] = users_qs.filter(is_staff=True).count()
        ctx["role_counts"] = (
            list(users_qs.values("role").annotate(c=Count("id")).order_by("-c"))
            if _model_has_field(User, "role")
            else []
        )
    except Exception as e:
        logger.exception("Users stats error: %s", e)
        ctx["users_total"] = 0
        ctx["users_staff"] = 0
        ctx["role_counts"] = []

    # ---- الطلبات
    ctx["req_counts"] = []
    ctx["req_recent"] = []
    try:
        if Request is not None:
            req_state = _pick_field(Request, ["state", "status", "phase"])
            req_created = _pick_field(Request, ["created_at", "created", "submitted_at"])
            req_assigned = _pick_field(Request, ["assigned_employee", "assigned_to"])
            req_requester = _pick_field(Request, ["client", "created_by"])

            # select_related ديناميكي على علاقة واحدة إن وجدت
            req_base = Request.objects.all()
            if req_requester:
                req_base = req_base.select_related(req_requester)

            # لا يوجد تصفية زمنية

            if req_state:
                agg = req_base.values(req_state).annotate(c=Count("id")).order_by("-c")
                ctx["req_counts"] = [{"state": row.get(req_state), "c": row["c"]} for row in agg]

            ctx["req_recent"] = req_base.order_by(f"-{req_created}" if req_created else "-id")[:10]

            # تنبيه طلبات جديدة غير مُسنّدة
            if req_state and req_assigned:
                try:
                    if req_base.filter(**{f"{req_assigned}__isnull": True, req_state: "NEW"}).exists():
                        ctx["ops_alerts"].append("طلبات جديدة غير مُسنّدة — رجاء الإسناد.")
                except Exception:
                    pass
    except Exception as e:
        logger.exception("Requests stats error: %s", e)

    # ---- الفواتير
    ctx["inv_totals"] = {"total": Decimal("0.00"), "paid": Decimal("0.00"), "unpaid": Decimal("0.00")}
    ctx["inv_recent"] = []
    ctx["overdue_count"] = 0
    try:
        if Invoice is not None:
            amount_f = None
            # ابحث فقط عن أول حقل من نوع DecimalField
            for f in ["amount", "total", "grand_total"]:
                try:
                    field_obj = Invoice._meta.get_field(f)
                    if isinstance(field_obj, DecimalField):
                        amount_f = f
                        break
                except Exception:
                    continue
            paid_flag = _pick_field(Invoice, ["is_paid", "paid"])
            issued_f = _pick_field(Invoice, ["issued_at", "created_at", "created"])

            inv_base = Invoice.objects.all()
            # لا يوجد تصفية زمنية

            if amount_f:
                from django.db.models import DecimalField
                totals = inv_base.aggregate(
                    total=Coalesce(Sum(amount_f, output_field=DecimalField()), V(0)),
                    paid=Coalesce(
                        Sum(
                            amount_f,
                            filter=Q(**{paid_flag: True}) if paid_flag else Q(pk__in=[]),
                            output_field=DecimalField(),
                        ),
                        V(0),
                    ),
                )
                total = _money(totals["total"])
                paid = _money(totals["paid"])
                ctx["inv_totals"] = {"total": total, "paid": paid, "unpaid": total - paid}

            fields = _only_fields(Invoice, ["id", amount_f or "", paid_flag or "", "agreement_id"])
            if not fields:
                fields = ["id"]
            ctx["inv_recent"] = inv_base.select_related("agreement").only(*fields).order_by(
                f"-{issued_f}" if issued_f else "-id"
            )[:10]

            # تنبيه تأخر (>3 أيام)
            if issued_f and paid_flag:
                overdue = inv_base.filter(
                    **{paid_flag: False, f"{issued_f}__lt": date.today() - timedelta(days=3)}
                ).count()
                ctx["overdue_count"] = overdue
                if overdue:
                    ctx["ops_alerts"].append(f"هناك {overdue} فاتورة متأخرة عن السداد.")
    except Exception as e:
        logger.exception("Invoices stats error: %s", e)

    # ---- الاتفاقيات + العروض
    ctx["agreements_total"] = 0
    ctx["agreements_recent"] = []
    ctx["offers_total"] = 0
    try:
        if Agreement is not None:
            ag_created = _pick_field(Agreement, ["created_at", "created", "approved_at"])
            ag_status = _pick_field(Agreement, ["status", "state"])
            ag_base = Agreement.objects.all()
            # لا يوجد تصفية زمنية
            ctx["agreements_total"] = ag_base.count()
            fields = _only_fields(Agreement, ["id", "title", ag_status or ""])
            if not fields:
                fields = ["id"]
            ctx["agreements_recent"] = ag_base.only(*fields).order_by(f"-{ag_created}" if ag_created else "-id")[:10]

        if Offer is not None:
            off_created = _pick_field(Offer, ["created_at", "created"])
            off_base = Offer.objects.all()
            # لا يوجد تصفية زمنية
            ctx["offers_total"] = off_base.count()
    except Exception as e:
        logger.exception("Agreements/Offers stats error: %s", e)

    # ---- النزاعات
    ctx["disputes_recent"] = []
    try:
        if Dispute is not None:
            d_created = _pick_field(Dispute, ["created_at", "created", "opened_at"])
            d_status = _pick_field(Dispute, ["status", "state"])
            fields = _only_fields(Dispute, ["id", d_status or "", "title", "note"])
            if not fields:
                fields = ["id"]
            d_base = Dispute.objects.all()
            # لا يوجد تصفية زمنية
            ctx["disputes_recent"] = d_base.only(*fields).order_by(f"-{d_created}" if d_created else "-id")[:10]

            # SLA: نزاعات عمرها >3 أيام
            if d_created:
                aged = d_base.filter(**{f"{d_created}__lt": date.today() - timedelta(days=3)}).count()
                if aged:
                    ctx["ops_alerts"].append(f"نزاعات متأخرة للمراجعة: {aged}.")
    except Exception as e:
        logger.exception("Disputes stats error: %s", e)

    # أفعال سريعة (تعتمد توافر الروابط)
    ctx["quick"] = [
        {"label": "إدارة الفواتير", "url": ctx["urls"]["invoices"], "icon": "fa-receipt"},
        {"label": "عرض الطلبات", "url": ctx["urls"]["requests"], "icon": "fa-list"},
        {"label": "الاتفاقيات", "url": ctx["urls"]["agreements"], "icon": "fa-file-signature"},
        {"label": "النزاعات", "url": ctx["urls"]["disputes"], "icon": "fa-scale-balanced"},
        {"label": "المستخدمون", "url": ctx["urls"]["users"], "icon": "fa-users"},
    ]

    return render(request, "dashboard/admin_dashboard.html", ctx)


# ====================== إدارة الموظفين ======================

@login_required
def employees_list(request):
    if not _require_admin(request):
        return redirect("website:home")

    q = (request.GET.get("q") or "").strip()
    qs = User.objects.all()
    if _model_has_field(User, "role"):
        qs = qs.filter(role="employee")

    if q:
        filters = Q(username__icontains=q) | Q(email__icontains=q)
        if _model_has_field(User, "first_name"):
            filters |= Q(first_name__icontains=q)
        if _model_has_field(User, "last_name"):
            filters |= Q(last_name__icontains=q)
        if _model_has_field(User, "name"):
            filters |= Q(name__icontains=q)
        qs = qs.filter(filters)

    fields = _only_fields(User, ["id", "email", "name", "date_joined"])
    if not fields:
        fields = ["id"]
    order = "-date_joined" if _model_has_field(User, "date_joined") else "-id"
    qs = qs.only(*fields).order_by(order)

    page_obj = _paginate(request, qs, per_page=25)
    return render(request, "dashboard/employees.html", {"page_obj": page_obj, "q": q, "today": date.today()})


# ====================== إدارة العملاء ======================

@login_required
def clients_list(request):
    if not _require_admin(request):
        return redirect("website:home")

    q = (request.GET.get("q") or "").strip()
    qs = User.objects.all()
    if _model_has_field(User, "role"):
        qs = qs.filter(role="client")

    if q:
        filters = Q(username__icontains=q) | Q(email__icontains=q)
        if _model_has_field(User, "first_name"):
            filters |= Q(first_name__icontains=q)
        if _model_has_field(User, "last_name"):
            filters |= Q(last_name__icontains=q)
        if _model_has_field(User, "name"):
            filters |= Q(name__icontains=q)
        qs = qs.filter(filters)

    fields = _only_fields(User, ["id", "email", "name", "date_joined"])
    if not fields:
        fields = ["id"]
    order = "-date_joined" if _model_has_field(User, "date_joined") else "-id"
    qs = qs.only(*fields).order_by(order)

    page_obj = _paginate(request, qs, per_page=25)
    return render(request, "dashboard/clients.html", {"page_obj": page_obj, "q": q, "today": date.today()})


# ====================== إدارة الطلبات ======================

@login_required
def requests_list(request):
    if not _require_admin(request):
        return redirect("website:home")
    if Request is None:
        messages.warning(request, "تطبيق الطلبات غير متاح.")
        return render(request, "dashboard/requests.html", {"page_obj": None, "q": "", "state": "", "today": date.today()})

    q = (request.GET.get("q") or "").strip()
    wanted_state = (request.GET.get("state") or "").strip()
    d_from, d_to = _daterange(request)

    req_state = _pick_field(Request, ["state", "status", "phase"])
    req_created = _pick_field(Request, ["created_at", "created", "submitted_at"])
    req_requester = _pick_field(Request, ["client", "created_by"])

    # select_related ديناميكي
    qs = Request.objects.all()
    if req_requester:
        qs = qs.select_related(req_requester)

    # بحث
    if q:
        filters = Q(title__icontains=q) | Q(description__icontains=q)
        if _model_has_field(Request, "short_code"):
            filters |= Q(short_code__icontains=q)

        # بحث على صاحب الطلب إن وُجد
        if req_requester:
            # نفترض أن جهة المستخدم هي User؛ نتحقق من الحقول المتاحة على User
            if _model_has_field(User, "username"):
                filters |= Q(**{f"{req_requester}__username__icontains": q})
            if _model_has_field(User, "email"):
                filters |= Q(**{f"{req_requester}__email__icontains": q})
            if _model_has_field(User, "name"):
                filters |= Q(**{f"{req_requester}__name__icontains": q})

        qs = qs.filter(filters)

    # حالة
    if wanted_state and req_state:
        qs = qs.filter(**{req_state: wanted_state})

    # نطاق الزمن
    if req_created:
        qs = qs.filter(**{f"{req_created}__date__gte": d_from, f"{req_created}__date__lte": d_to})

    # Ensure select_related field is not deferred in .only()
    base_fields = ["id", "title", req_state or ""]
    if req_requester:
        base_fields.append(req_requester)
    fields = _only_fields(Request, base_fields)
    if not fields:
        fields = ["id"]
    qs = qs.only(*fields).order_by(f"-{req_created}" if req_created else "-id")

    page_obj = _paginate(request, qs, per_page=20)
    return render(
        request,
        "dashboard/requests.html",
        {"page_obj": page_obj, "q": q, "state": wanted_state, "from": d_from, "to": d_to, "today": date.today()},
    )


# ====================== إدارة النزاعات ======================

@login_required
def disputes_list(request):
    if not _require_admin(request):
        return redirect("website:home")
    if Dispute is None:
        messages.warning(request, "تطبيق النزاعات غير متاح.")
        return render(request, "dashboard/disputes.html", {"page_obj": None, "q": "", "status": "", "today": date.today()})

    q = (request.GET.get("q") or "").strip()
    status_val = (request.GET.get("status") or "").strip()
    d_from, d_to = _daterange(request)

    d_status = _pick_field(Dispute, ["status", "state"])
    d_created = _pick_field(Dispute, ["created_at", "created", "opened_at"])

    qs = Dispute.objects.all()

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(note__icontains=q))

    if status_val and d_status:
        qs = qs.filter(**{d_status: status_val})

    if d_created:
        qs = qs.filter(**{f"{d_created}__date__gte": d_from, f"{d_created}__date__lte": d_to})

    fields = _only_fields(Dispute, ["id", d_status or "", "title", "note"])
    if not fields:
        fields = ["id"]
    qs = qs.only(*fields).order_by(f"-{d_created}" if d_created else "-id")

    page_obj = _paginate(request, qs, per_page=20)
    return render(
        request,
        "dashboard/disputes.html",
        {"page_obj": page_obj, "q": q, "status": status_val, "from": d_from, "to": d_to, "today": date.today()},
    )
