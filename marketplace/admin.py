# marketplace/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import Count
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Request, Offer, Note


# ========= أدوات مساعدة للحالات =========

# أسماء قديمة/متعددة → الاسم المعياري (القيمة النصية بالحقل)
STATUS_ALIASES = {
    "offers": "offer_selected",
    "offer": "offer_selected",
    "offer_selected": "offer_selected",

    "agreement": "agreement_pending",
    "agreements": "agreement_pending",
    "agreement_pending": "agreement_pending",

    "working": "in_progress",
    "progress": "in_progress",
    "in_progress": "in_progress",

    "delivered": "delivered",
    "pending_review": "pending_review",
    "review": "pending_review",

    "completed": "completed",
    "done": "completed",
    "complete": "completed",

    "disputed": "disputed",

    "canceled": "cancelled",   # تهجئة أمريكية → بريطانية
    "cancelled": "cancelled",

    "new": "new",
}

BADGE_CLASSES = {
    "new": "bg-gray-100 text-gray-800",
    "offer_selected": "bg-sky-100 text-sky-800",
    "agreement_pending": "bg-indigo-100 text-indigo-800",
    "in_progress": "bg-amber-100 text-amber-800",
    "delivered": "bg-teal-100 text-teal-800",
    "pending_review": "bg-fuchsia-100 text-fuchsia-800",
    "completed": "bg-emerald-100 text-emerald-800",
    "disputed": "bg-rose-100 text-rose-800",
    "cancelled": "bg-slate-100 text-slate-700",
}

def _canon(value: str | None) -> str:
    """تطبيع القيمة النصية للحالة إلى اسم معياري."""
    v = (value or "").strip().lower()
    return STATUS_ALIASES.get(v, v)

def _status_val(name: str, fallback: str) -> str:
    """
    إرجاع قيمة الحالة:
    - إن وُجدت TextChoices على Request.Status نستخدمها.
    - خلاف ذلك نرجع fallback (بعد التطبيع).
    """
    fallback_canon = _canon(fallback)
    Status = getattr(Request, "Status", None)
    if Status is not None:
        return getattr(Status, name, fallback_canon)
    return fallback_canon

def _safe_update_status(modeladmin, request, queryset, new_status_value: str, success_msg: str):
    """
    إجراء إداري لتحديث حالة الطلب بأمان مع رسائل واضحة.
    new_status_value يجب أن يكون القيمة النهائية (نص الحقل) بعد التطبيع.
    """
    new_status_value = _canon(new_status_value)
    updated = 0
    for obj in queryset.select_related("client", "assigned_employee"):
        try:
            # منطق تجميد/تحرير الدفعات عند النزاع (اختياري إن وُجد)
            if new_status_value == "disputed" and hasattr(obj, "freeze_payouts"):
                obj.freeze_payouts()
            obj.status = new_status_value
            obj.save(update_fields=["status"])
            updated += 1
        except Exception as exc:
            messages.error(request, _(f"فشل تحديث الطلب #{obj.pk}: {exc}"))
    if updated:
        messages.success(request, _(success_msg.format(count=updated)))


# ========= فلاتر مخصّصة =========

class OfferCountListFilter(admin.SimpleListFilter):
    title = _("عدد العروض")
    parameter_name = "offers_count"

    def lookups(self, request, model_admin):
        return [
            ("0", _("بدون عروض")),
            ("1", _("عرض واحد")),
            ("2+", _("عرضان فأكثر")),
        ]

    def queryset(self, request, queryset):
        qs = queryset.annotate(_offers=Count("offers"))
        val = self.value()
        if val == "0":
            return qs.filter(_offers=0)
        if val == "1":
            return qs.filter(_offers=1)
        if val == "2+":
            return qs.filter(_offers__gte=2)
        return queryset


# ========= Inlines =========

class OfferInline(admin.TabularInline):
    model = Offer
    extra = 0
    fields = ("employee", "proposed_price", "status", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("employee",)
    show_change_link = True

class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ("author", "is_internal", "text", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("author",)


# ========= RequestAdmin =========

@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "client",
        "assigned_employee",
        "colored_status",
        "total_offers",
        "created_at",
    )
    list_filter = (
        "status",
        OfferCountListFilter,
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "id",
        "title",
        "details",
        "client__email",
        "client__username",
        "assigned_employee__email",
        "assigned_employee__username",
    )
    autocomplete_fields = ("client", "assigned_employee")
    inlines = (OfferInline, NoteInline)
    list_select_related = ("client", "assigned_employee")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": (
                "title",
                "details",
                ("client", "assigned_employee"),
                "status",
            )
        }),
        (_("تتبّع زمني"), {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )

    # تحسين الأداء
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("client", "assigned_employee").prefetch_related("offers")

    # عرض ملوّن للحالة بدون اعتماد على ثوابت Status
    @admin.display(description=_("الحالة"))
    def colored_status(self, obj: Request):
        value = _canon(getattr(obj, "status", ""))
        cls = BADGE_CLASSES.get(value, "bg-gray-100 text-gray-800")
        # إن وُجد get_status_display نستخدم النص البشري
        disp = getattr(obj, "get_status_display", None)
        label = disp() if callable(disp) else (value or "—")
        return format_html('<span class="px-2 py-1 rounded-md text-xs {}">{}</span>', cls, label)

    @admin.display(description=_("العروض"))
    def total_offers(self, obj: Request):
        # relies on related_name="offers" وإلا fallback للـ offer_set
        if hasattr(obj, "offers"):
            return obj.offers.count()
        return obj.offer_set.count()

    # ========= إجراءات تغيير الحالة (مرنة) =========
    actions = [
        "action_mark_new",
        "action_mark_offers",
        "action_mark_agreement_pending",
        "action_mark_in_progress",
        "action_mark_delivered",
        "action_mark_pending_review",
        "action_mark_completed",
        "action_mark_disputed",
        "action_mark_cancelled",
    ]

    @admin.action(description=_("تعيين الحالة: جديد"))
    def action_mark_new(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("NEW", "new"), "تم تحديث {count} إلى جديد.")

    @admin.action(description=_("تعيين الحالة: استقبال عروض"))
    def action_mark_offers(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("OFFERS", "offer_selected"), "تم تحديث {count} إلى استقبال عروض.")

    @admin.action(description=_("تعيين الحالة: انتظار اتفاقية"))
    def action_mark_agreement_pending(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("AGREEMENT_PENDING", "agreement_pending"), "تم تحديث {count} إلى انتظار اتفاقية.")

    @admin.action(description=_("تعيين الحالة: قيد التنفيذ"))
    def action_mark_in_progress(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("IN_PROGRESS", "in_progress"), "تم تحديث {count} إلى قيد التنفيذ.")

    @admin.action(description=_("تعيين الحالة: تم التسليم"))
    def action_mark_delivered(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("DELIVERED", "delivered"), "تم تحديث {count} إلى تم التسليم.")

    @admin.action(description=_("تعيين الحالة: بانتظار المراجعة"))
    def action_mark_pending_review(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("PENDING_REVIEW", "pending_review"), "تم تحديث {count} إلى بانتظار المراجعة.")

    @admin.action(description=_("تعيين الحالة: مكتمل"))
    def action_mark_completed(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("COMPLETED", "completed"), "تم تحديث {count} إلى مكتمل.")

    @admin.action(description=_("تعيين الحالة: نزاع (تجميد تلقائي)"))
    def action_mark_disputed(self, request, queryset):
        _safe_update_status(self, request, queryset, _status_val("DISPUTED", "disputed"), "تم تحديث {count} إلى نزاع وتم التجميد.")

    @admin.action(description=_("تعيين الحالة: ملغي"))
    def action_mark_cancelled(self, request, queryset):
        # ندعم التهجئتين
        val = _status_val("CANCELLED", "cancelled")
        if val == "cancelled":
            val = _status_val("CANCELED", "cancelled")
        _safe_update_status(self, request, queryset, val, "تم تحديث {count} إلى ملغي.")


# ========= OfferAdmin =========

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("id", "request", "employee", "proposed_price", "status", "created_at")
    list_filter = ("status", ("created_at", admin.DateFieldListFilter))
    search_fields = ("note", "employee__email", "employee__username", "request__title", "request__id")
    autocomplete_fields = ("request", "employee")
    list_select_related = ("request", "employee")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {
            "fields": (
                "request",
                "employee",
                "proposed_price",
                "status",
                "note",
            )
        }),
        (_("تتبّع زمني"), {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("request", "employee")

    def save_model(self, request, obj, form, change):
        """
        – يضمن "عرض واحد لكل تقني على نفس الطلب".
        – يحافظ على سلامة البيانات ويظهر رسالة واضحة.
        """
        exists = (
            Offer.objects
            .filter(request=obj.request, employee=obj.employee)
            .exclude(pk=obj.pk if obj.pk else None)
            .exists()
        )
        if exists:
            messages.error(request, _("لا يمكن تقديم أكثر من عرض واحد لنفس الطلب من نفس التقني."))
            return  # لا يحفظ
        super().save_model(request, obj, form, change)


# ========= NoteAdmin =========

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("id", "request", "author", "is_internal", "created_at")
    list_filter = ("is_internal", ("created_at", admin.DateFieldListFilter))
    search_fields = ("text", "author__email", "author__username", "request__title", "request__id")
    autocomplete_fields = ("request", "author", "parent")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("request", "author", "is_internal", "text", "parent")}),
        (_("تتبّع زمني"), {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )
