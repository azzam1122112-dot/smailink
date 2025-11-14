# config/asgi.py
# -*- coding: utf-8 -*-
"""
ASGI config for config project.

يوفّر نقطة الدخول لتطبيق ASGI مع دعم HTTP افتراضيًا،
ودعم WebSocket عبر Django Channels إن كانت مُثبّتة.
-Fallback آمن-: إذا لم تتوفر Channels، يعمل التطبيق على HTTP فقط.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# تطبيق Django القياسي (HTTP)
from django.core.asgi import get_asgi_application

# استخدم تطبيق ASGI القياسي الخاص بـ Django (بلا Channels)
application = get_asgi_application()
