from __future__ import annotations
from django.contrib import admin, messages
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "title", "is_read", "created_at", "actor")
    list_filter = ("is_read", "created_at")
    search_fields = ("title", "body", "recipient__username", "recipient__name", "recipient__email")
    autocomplete_fields = ("recipient", "actor")
    readonly_fields = ("created_at",)
    list_select_related = ("recipient", "actor")

    actions = ("mark_as_read", "mark_as_unread")

    @admin.action(description="تعليم كمقروء")
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"تم تعليم {updated} تنبيه/تنبيهات كمقروءة.", level=messages.SUCCESS)

    @admin.action(description="تعليم كغير مقروء")
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"تم تعليم {updated} تنبيه/تنبيهات كغير مقروءة.", level=messages.INFO)
