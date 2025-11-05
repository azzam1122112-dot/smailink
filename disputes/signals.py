# disputes/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from disputes.models import Dispute
from marketplace.models import Request

@receiver(post_save, sender=Dispute)
def on_dispute_opened(sender, instance: Dispute, created, **kwargs):
    if created and instance.is_open:
        # تجميد الطلب: حالة=DISPUTED، is_frozen=True
        req = instance.request
        req.freeze()
        # (اختياري) إشعار المدير والمالية والطرفين — استخدم نظام الإشعارات لديك
