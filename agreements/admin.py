from django.contrib import admin
from .models import Agreement, Milestone, AgreementClause, AgreementClauseItem

@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ("id", "request", "employee", "title", "total_amount", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "request__id", "employee__username", "employee__email")
    autocomplete_fields = ("request", "employee")

@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("id", "agreement", "order", "title", "amount", "status", "delivered_at", "approved_at", "paid_at")
    list_filter = ("status",)
    search_fields = ("title", "agreement__title")
    autocomplete_fields = ("agreement",)

@admin.register(AgreementClause)
class AgreementClauseAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("key", "title")

@admin.register(AgreementClauseItem)
class AgreementClauseItemAdmin(admin.ModelAdmin):
    list_display = ("id", "agreement", "position", "clause")
    search_fields = ("agreement__title", "clause__title", "custom_text")
    autocomplete_fields = ("agreement", "clause")
