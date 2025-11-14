# config/routing.py
# -*- coding: utf-8 -*-
"""
تعريف مسارات WebSocket على مستوى المشروع.
ملاحظة: أبقينا القائمة فارغة افتراضيًا لتجنّب أخطاء الاستيراد
إذا لم تكن تطبيقات المستهلكين (consumers) موجودة بعد.
عند إضافة مستهلكات لاحقًا (مثل ThreadConsumer)، فعِّل التعريفات المعلّقة أدناه.
"""

from django.urls import re_path

# عند إنشاء مستهلك (Consumer) لاحقًا:
# from messaging.consumers import ThreadConsumer

websocket_urlpatterns = [
    # مثال لاحق للتفعيل بعد إضافة messaging:
    # re_path(r"^ws/thread/(?P<thread_id>\d+)/$", ThreadConsumer.as_asgi()),
]
