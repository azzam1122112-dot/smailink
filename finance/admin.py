# finance/admin.py
from __future__ import annotations
from .models import Invoice, FinanceSettings, Payout, TaxRemittance

from django.contrib import admin, messages
from django.utils import timezone
from django.db import transaction
from django.utils.html import format_html
from django.urls import reverse, NoReverseMatch

from .models import Invoice, FinanceSettings, Payout


# ===========================
#  FinanceSettings (Singleton)
# ===========================
@admin.register(FinanceSettings)
class FinanceSettingsAdmin(admin.ModelAdmin):
    list_display = ("platform_fee_percent", "vat_rate", "updated_at")
    readonly_fields = ("updated_at",)
    list_per_page = 20

    def has_add_permission(self, request):
        """
        السماح بإضافة سجل واحد فقط (Singleton).
        """
        if FinanceSettings.objects.exists():
            return False
        return super().has_add_permission(request)


# =============
#  Payout Admin
# =============
@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "amount",
        "status",
        "method",
        "ref_code",
        "issued_at",
        "paid_at",
    )
    list_filter = ("status", "method", "issued_at", "paid_at")
    search_fields = (
        "ref_code",
        "note",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
        "employee__name",
    )
    date_hierarchy = "issued_at"
    readonly_fields = ("issued_at", "updated_at")
    list_per_page = 50

    def get_queryset(self, request):
        # تحسين الأداء بالـ select_related
        qs = super().get_queryset(request)
        return qs.select_related("employee")

    actions = ("mark_selected_paid", "mark_selected_cancelled")

    @admin.action(description="وسم أوامر الصرف المختارة كـ «مدفوعة» الآن")
    def mark_selected_paid(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for p in queryset.select_for_update():
                if p.status != Payout.Status.PAID:
                    p.mark_paid(method=p.method or "admin", ref=p.ref_code or "")
                    updated += 1
        if updated:
            self.message_user(request, f"تم وسم {updated} أمر/أوامر صرف كمدفوعة.", level=messages.SUCCESS)
        else:
            self.message_user(request, "لا توجد سجلات لوسمها (قد تكون جميعها مدفوعة).", level=messages.INFO)

    @admin.action(description="وسم أوامر الصرف المختارة كـ «ملغاة»")
    def mark_selected_cancelled(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for p in queryset.select_for_update():
                if p.status != Payout.Status.CANCELLED:
                    p.status = Payout.Status.CANCELLED
                    if not p.paid_at:
                        # لا نضبط paid_at عند الإلغاء
                        pass
                    p.save(update_fields=["status", "updated_at"])
                    updated += 1
        if updated:
            self.message_user(request, f"تم إلغاء {updated} أمر/أوامر صرف.", level=messages.SUCCESS)
        else:
            self.message_user(request, "لا توجد سجلات مناسبة للإلغاء.", level=messages.INFO)


# ==============
#  Invoice Admin
# ==============
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """
    إدارة الفواتير: تدعم وسم الدفع، الإلغاء، وإعادة احتساب المشتقات.
    تعرض أعمدة مساعدة لسهولة تتبع الطلب/الاتفاقية.
    """
    list_display = (
        "id",
        "agreement_link",
        "request_link",
        "milestone",
        "amount",
        "platform_fee_amount",
        "vat_amount",
        "subtotal",
        "total_amount",
        "status",
        "issued_at",
        "paid_at",
        "method",
        "ref_code",
        "paid_ref",
        "is_overdue_badge",
    )
    list_filter = ("status", "method", "issued_at", "paid_at")
    search_fields = (
        "id",
        "ref_code",
        "paid_ref",
        "agreement__id",
        "agreement__request__id",
        "milestone__title",
    )
    date_hierarchy = "issued_at"
    list_per_page = 50

    readonly_fields = (
        "subtotal",
        "total_amount",
        "platform_fee_amount",
        "vat_amount",
        "issued_at",
        "paid_at",
        "updated_at",
    )

    fieldsets = (
        ("الارتباطات", {
            "fields": ("agreement", "milestone", "created_by"),
        }),
        ("المبالغ الأساسية والنِّسب", {
            "fields": (
                "amount",
                "platform_fee_percent",
                "vat_percent",
            ),
            "description": "تُعاد احتساب المشتقات تلقائيًا عند الحفظ.",
        }),
        ("المشتقات المحسوبة", {
            "fields": (
                "platform_fee_amount",
                "subtotal",
                "vat_amount",
                "total_amount",
            ),
        }),
        ("الحالة والتواريخ", {
            "fields": ("status", "issued_at", "due_at", "paid_at", "updated_at"),
        }),
        ("بيانات الدفع والمرجع", {
            "fields": ("method", "ref_code", "paid_ref"),
        }),
    )

    def get_queryset(self, request):
        # تحسين الأداء
        qs = super().get_queryset(request)
        return qs.select_related("agreement", "agreement__request", "milestone")

    # روابط مساعدة للانتقال السريع من لوحة الإدارة
    @admin.display(description="الاتفاقية", ordering="agreement_id")
    def agreement_link(self, obj: Invoice):
        try:
            url = reverse("admin:agreements_agreement_change", args=[obj.agreement_id])
            return format_html('<a href="{}">A{}</a>', url, obj.agreement_id)
        except Exception:
            return f"A{obj.agreement_id}"

    @admin.display(description="الطلب", ordering="agreement__request__id")
    def request_link(self, obj: Invoice):
        req_id = getattr(getattr(obj, "agreement", None), "request_id", None)
        if not req_id:
            return "-"
        # نحاول ربط صفحة الطلب في الإدارة إن وُجدت
        try:
            url = reverse("admin:marketplace_request_change", args=[req_id])
            return format_html('<a href="{}">R{}</a>', url, req_id)
        except NoReverseMatch:
            # أو رابط الواجهة العامة إن وُجد
            try:
                url2 = reverse("marketplace:request_detail", kwargs={"pk": req_id})
                return format_html('<a href="{}" target="_blank">R{}</a>', url2, req_id)
            except Exception:
                return f"R{req_id}"

    @admin.display(description="متأخرة؟")
    def is_overdue_badge(self, obj: Invoice):
        try:
            if obj.is_overdue:
                return format_html('<span style="color:#b91c1c;font-weight:bold">متأخرة</span>')
            return format_html('<span style="color:#065f46">-</span>')
        except Exception:
            return "-"

    actions = (
        "action_mark_paid_now",
        "action_cancel",
        "action_recompute_totals",
        "action_export_selected_csv",
    )

    @admin.action(description="وسم الفواتير المختارة كـ «مدفوعة» الآن")
    def action_mark_paid_now(self, request, queryset):
        updated = 0
        now = timezone.now()
        with transaction.atomic():
            for inv in queryset.select_for_update():
                if inv.status != Invoice.Status.PAID and (inv.total_amount or 0) > 0:
                    inv.mark_paid(paid_at=now, save=True)
                    updated += 1
        if updated:
            self.message_user(request, f"تم وسم {updated} فاتورة/فواتير كمدفوعة.", level=messages.SUCCESS)
        else:
            self.message_user(request, "لا توجد فواتير مناسبة لوسمها.", level=messages.INFO)

    @admin.action(description="إلغاء الفواتير المختارة")
    def action_cancel(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for inv in queryset.select_for_update():
                if inv.status != Invoice.Status.CANCELLED:
                    inv.cancel(save=True)
                    updated += 1
        if updated:
            self.message_user(request, f"تم إلغاء {updated} فاتورة/فواتير.", level=messages.SUCCESS)
        else:
            self.message_user(request, "لا توجد فواتير مناسبة للإلغاء.", level=messages.INFO)

    @admin.action(description="إعادة احتساب الإجماليات للفواتير المختارة")
    def action_recompute_totals(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for inv in queryset.select_for_update():
                inv.recompute_totals()
                inv.save(update_fields=[
                    "platform_fee_amount",
                    "subtotal",
                    "vat_amount",
                    "total_amount",
                    "updated_at",
                ])
                updated += 1
        if updated:
            self.message_user(request, f"تمت إعادة احتساب الإجماليات لـ {updated} فاتورة/فواتير.", level=messages.SUCCESS)
        else:
            self.message_user(request, "لم يتم تحديث أي سجلات.", level=messages.INFO)

    @admin.action(description="تصدير الفواتير المختارة إلى CSV (سريع)")
    def action_export_selected_csv(self, request, queryset):
        """
        تصدير بسيط من داخل لوحة الإدارة — يُستخدم عند الحاجة لتصدير subset سريع.
        للتصدير الكامل مع مرشحات الفترة استخدم: finance:export_invoices_csv من الواجهة.
        """
        import csv
        from django.http import HttpResponse

        qs = queryset.select_related("agreement", "agreement__request", "milestone").order_by("-paid_at", "-issued_at")
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="selected_invoices.csv"'
        w = csv.writer(resp)
        w.writerow(["InvoiceID", "AgreementID", "RequestID", "Milestone", "Amount", "Status",
                    "IssuedAt", "PaidAt", "Method", "RefCode", "PaidRef"])
        for inv in qs:
            w.writerow([
                inv.id,
                inv.agreement_id,
                getattr(getattr(inv, "agreement", None), "request_id", ""),
                getattr(getattr(inv, "milestone", None), "title", "") if getattr(inv, "milestone_id", None) else "",
                f"{inv.amount}",
                inv.get_status_display() if hasattr(inv, "get_status_display") else getattr(inv, "status", ""),
                inv.issued_at.strftime("%Y-%m-%d %H:%M") if getattr(inv, "issued_at", None) else "",
                inv.paid_at.strftime("%Y-%m-%d %H:%M") if getattr(inv, "paid_at", None) else "",
                getattr(inv, "method", "") or "",
                getattr(inv, "ref_code", "") or "",
                getattr(inv, "paid_ref", "") or "",
            ])
        return resp
# ===========================
#  TaxRemittance Admin
# ===========================
@admin.register(TaxRemittance)
class TaxRemittanceAdmin(admin.ModelAdmin):
    list_display = ("id", "amount", "status", "period_from", "period_to", "ref_code", "created_at", "sent_at")
    list_filter = ("status", "created_at", "sent_at")
    search_fields = ("ref_code", "note")
    readonly_fields = ("created_at", "updated_at")
    actions = ("mark_selected_sent",)

    @admin.action(description="وسم التوريدات المختارة كـ «تم التوريد»")
    def mark_selected_sent(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for tr in queryset.select_for_update():
                if tr.status != TaxRemittance.Status.SENT:
                    tr.mark_sent(ref=tr.ref_code or "")
                    updated += 1
        if updated:
            self.message_user(request, f"تم وسم {updated} توريد/توريدات كـ «تم التوريد».", level=messages.SUCCESS)
