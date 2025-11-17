# disputes/urls.py
from __future__ import annotations

from django.shortcuts import redirect
from django.urls import path

from . import views

app_name = "disputes"

# ======================
# Helpers / Compat Aliases (توافق لمسارات قديمة)
# ======================
def open_alias_r(request, request_id: int):
    """
    توافق قديم:
      r/<int:request_id>/dispute/open/  →  disputes:open (request/<id>/open/)
    """
    return redirect("disputes:open", request_id=request_id)


def open_alias_short(request, request_id: int):
    """
    توافق قديم:
      open/<int:request_id>/  →  disputes:open (request/<id>/open/)
    """
    return redirect("disputes:open", request_id=request_id)


def detail_alias_id(request, pk: int):
    """
    توافق قديم:
      d/<int:pk>/  →  disputes:detail
    """
    return redirect("disputes:detail", pk=pk)


def update_status_alias(request, pk: int):
    """
    توافق قديم:
      d/<int:pk>/status/  →  disputes:update_status
    """
    return redirect("disputes:update_status", pk=pk)


# ======================
# Resolve optional views (نختار الدوال المتوفرة بدون كسر الكود)
# ======================
open_view = getattr(views, "dispute_open", None) or getattr(views, "dispute_create", None)
detail_view = getattr(views, "dispute_detail", None)
my_list_view = getattr(views, "my_disputes", None)
admin_list_view = getattr(views, "dispute_list", None)

urlpatterns: list = []

# ======================
# مسارات أساسية ثابتة
# ======================
# تحديث حالة النزاع (حل/إلغاء/إعادة فتح) — للمسؤولين فقط
urlpatterns.append(
    path("<int:pk>/update-status/", views.dispute_update_status, name="update_status")
)

# فتح نزاع انطلاقاً من الطلب — نوفر اسمين لضمان التوافق:
#   disputes:open            ← الاسم الشائع في القوالب
#   disputes:open_by_request ← اسم بديل لمن يستخدمه سابقاً
if open_view:
    urlpatterns += [
        path("request/<int:request_id>/open/", open_view, name="open"),
        path("request/<int:request_id>/open/", open_view, name="open_by_request"),
    ]

# تفاصيل النزاع (اختياري)
if detail_view:
    urlpatterns.append(path("<int:pk>/", detail_view, name="detail"))

# القوائم (اختياري)
if my_list_view:
    urlpatterns.append(path("mine/", my_list_view, name="mine"))

if admin_list_view:
    urlpatterns.append(path("all/", admin_list_view, name="list"))

# ======================
# Aliases للتوافق العكسي مع روابط قديمة
# ======================
urlpatterns += [
    # أمثلة روابط قديمة تم رصدها بالمشروع/القوالب
    path("r/<int:request_id>/dispute/open/", open_alias_r, name="open_alias_r"),
    path("open/<int:request_id>/", open_alias_short, name="open_alias_short"),
    path("d/<int:pk>/", detail_alias_id, name="detail_alias_id"),
    path("d/<int:pk>/status/", update_status_alias, name="update_status_alias"),
    path("<int:pk>/", views.dispute_detail, name="detail"),

]
