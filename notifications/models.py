from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse


class Notification(models.Model):
    """
    تنبيه داخلي بسيط قابل للربط بأي كيان (اختياري).
    يدعم رابط فتح (URL) + ربط عام GenericForeignKey.
    """

    # المستلم (مطلوب)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    # فاعل الإجراء (اختياري)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actor_notifications",
    )

    # نصوص التنبيه
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    # رابط اختياري يفتح له التنبيه (مثلاً تفاصيل الطلب/الاتفاقية/الفاتورة)
    url = models.CharField(max_length=512, blank=True)

    # ربط عام اختياري بأي Model
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self) -> str:  # آمن للطباعة/السجلات
        return f"{self.recipient} → {self.title}"

    def get_absolute_url(self) -> str:
        """
        إن لم يكن هناك url مخصّص، نوجّه لقائمة التنبيهات.
        """
        return self.url or reverse("notifications:list")

    # أدوات مساعدة صغيرة
    def mark_read(self, save: bool = True) -> None:
        if not self.is_read:
            self.is_read = True
            if save:
                self.save(update_fields=["is_read"])

    @staticmethod
    def unread_count_for(user) -> int:
        return Notification.objects.filter(recipient=user, is_read=False).count()
