# marketplace/middleware.py
import re
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

EMAIL_RE   = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.I)
PHONE_RE   = re.compile(r"(?<!\d)(?:\+?\d[\d\s\-]{7,}\d)")
URL_RE     = re.compile(r"(?:https?://|www\.)\S+", re.I)
HANDLE_RE  = re.compile(r"(?<!\w)@[A-Za-z0-9_]{3,}")

MASK_TOKEN = "••••••"

def _mask(text: str) -> str:
    # نستبدل فقط القيم المطابقة — لا نلمس بقية الـHTML
    text = EMAIL_RE.sub(MASK_TOKEN, text)
    text = PHONE_RE.sub(MASK_TOKEN, text)
    text = URL_RE.sub(MASK_TOKEN, text)
    text = HANDLE_RE.sub(MASK_TOKEN, text)
    return text

class ContactMaskingMiddleware(MiddlewareMixin):
    """
    إخفاء بيانات تواصل العميل أثناء نافذة العروض فقط.
    لا نطبّق إلا على صفحات HTML المحددة، ولا نلمس JSON/CSS/JS.
    """

    def process_response(self, request, response):
        try:
            if not getattr(settings, "HIDE_CLIENT_CONTACT_DURING_OFFERS", True):
                return response

            ctype = response.headers.get("Content-Type", "")
            if "text/html" not in ctype:
                return response

            # نطاق التطبيق المستهدف فقط — عدّل المسارات حسب مشروعك
            path = request.path or ""
            if not (
                path.startswith("/marketplace/requests")
                or path.startswith("/marketplace/request")
                or path.startswith("/requests")
            ):
                return response

            # لا نطبّق على لوحة الإدارة
            if path.startswith("/admin"):
                return response

            # لا نطبّق على المستخدمين الـstaff
            user = getattr(request, "user", None)
            if user and user.is_authenticated and user.is_staff:
                return response

            # لا نلمس الردود المرمّزة (gzip/…)
            if response.has_header("Content-Encoding"):
                return response

            # فقط لو المحتوى نصي عادي
            content = response.content.decode(response.charset, errors="ignore")

            # تطبيق الإخفاء “فقط على المطابقات”
            masked = _mask(content)

            # لا تغيّر الترميز/الطول إن أمكن
            response.content = masked.encode(response.charset)
            response["Content-Length"] = str(len(response.content))
            return response
        except Exception:
            # في حال أي خطأ، لا نكسر الصفحة
            return response
