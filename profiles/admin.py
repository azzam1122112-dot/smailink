from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import EmployeeProfile, PortfolioItem, KYCStatus


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user", "title", "specialty", "city",
        "rating", "reviews_count",
        "kyc_status", "public_visible", "updated_at",
    )
    list_filter = ("public_visible", "kyc_status", "city")
    search_fields = ("user__name", "user__email", "title", "specialty", "skills", "city", "slug")
    readonly_fields = ("slug", "kyc_verified_at", "created_at", "updated_at")
    autocomplete_fields = ()
    ordering = ("-updated_at",)

    actions = ["mark_kyc_verified", "mark_kyc_pending", "mark_kyc_rejected", "toggle_public_visibility"]

    @admin.action(description="توثيق KYC للصفوف المحددة")
    def mark_kyc_verified(self, request, queryset):
        updated = queryset.update(kyc_status=KYCStatus.VERIFIED)
        self.message_user(request, f"تم توثيق {updated} بروفايل.")

    @admin.action(description="تعيين KYC: قيد المراجعة")
    def mark_kyc_pending(self, request, queryset):
        updated = queryset.update(kyc_status=KYCStatus.PENDING)
        self.message_user(request, f"تم تحديث حالة {updated} بروفايل إلى قيد المراجعة.")

    @admin.action(description="رفض KYC")
    def mark_kyc_rejected(self, request, queryset):
        updated = queryset.update(kyc_status=KYCStatus.REJECTED)
        self.message_user(request, f"تم رفض {updated} بروفايل.")

    @admin.action(description="تبديل الظهور العام On/Off")
    def toggle_public_visibility(self, request, queryset):
        cnt_on = queryset.filter(public_visible=True).count()
        cnt_off = queryset.filter(public_visible=False).count()
        queryset.filter(public_visible=True).update(public_visible=False)
        queryset.filter(public_visible=False).update(public_visible=True)
        self.message_user(request, f"تم إخفاء {cnt_on} وإظهار {cnt_off} بروفايل.")


@admin.register(PortfolioItem)
class PortfolioItemAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "is_public", "sort_order", "updated_at")
    list_filter = ("is_public",)
    search_fields = ("title", "owner__name", "tags")
    ordering = ("sort_order", "-updated_at")
