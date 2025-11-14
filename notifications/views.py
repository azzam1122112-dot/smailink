from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification


@login_required
def list_view(request: HttpRequest) -> HttpResponse:
    """
    قائمة التنبيهات (الأحدث أولاً) مع ترقيم.
    فلاتر بسيطة: status=unread|read|all (افتراضي all)
    """
    status_q = (request.GET.get("status") or "all").lower()
    qs = Notification.objects.filter(recipient=request.user)

    if status_q == "unread":
        qs = qs.filter(is_read=False)
    elif status_q == "read":
        qs = qs.filter(is_read=True)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "notifications/notifications_list.html",
        {"page_obj": page_obj, "status_q": status_q},
    )


@login_required
def detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    عرض تنبيه مفرد (يُعلّم كمقروء تلقائيًا ثم يوجّه للرابط إن وُجد).
    """
    n = get_object_or_404(Notification, pk=pk)
    if n.recipient_id != request.user.id:
        return HttpResponseForbidden("غير مسموح")

    if not n.is_read:
        n.mark_read(save=True)

    # إن وُجد رابط → نحيله له، وإلا نعرض بطاقة التنبيه
    if n.url:
        return redirect(n.get_absolute_url())

    return render(request, "notifications/notification_detail.html", {"n": n})


@login_required
def mark_read(request: HttpRequest, pk: int) -> HttpResponse:
    """
    تعليم تنبيه محدّد كمقروء.
    """
    n = get_object_or_404(Notification, pk=pk)
    if n.recipient_id != request.user.id:
        return HttpResponseForbidden("غير مسموح")
    if not n.is_read:
        n.mark_read(save=True)
    messages.success(request, "تم تعليم التنبيه كمقروء.")
    return redirect(request.GET.get("next") or "notifications:list")


@login_required
def mark_all_read(request: HttpRequest) -> HttpResponse:
    """
    تعليم جميع تنبيهات المستخدم كمقروءة (تحديث دفعي).
    """
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "تم تعليم جميع التنبيهات كمقروءة.")
    return redirect(request.GET.get("next") or "notifications:list")


@login_required
def delete(request: HttpRequest, pk: int) -> HttpResponse:
    """
    حذف تنبيه مفرد.
    """
    n = get_object_or_404(Notification, pk=pk)
    if n.recipient_id != request.user.id and not request.user.is_staff:
        return HttpResponseForbidden("غير مسموح")
    n.delete()
    messages.warning(request, "تم حذف التنبيه.")
    return redirect(request.GET.get("next") or "notifications:list")


@login_required
def delete_all(request: HttpRequest) -> HttpResponse:
    """
    حذف جميع التنبيهات (للمستخدم الحالي فقط).
    """
    Notification.objects.filter(recipient=request.user).delete()
    messages.warning(request, "تم حذف جميع التنبيهات.")
    return redirect("notifications:list")

from django.views.decorators.http import require_GET, require_POST
from django.http import JsonResponse
from django.utils.html import strip_tags

# ... (بقية الاستيرادات وواجهات العرض الحالية)

@login_required
@require_GET
def api_unread_count(request: HttpRequest) -> JsonResponse:
    """
    API: إرجاع عدد التنبيهات غير المقروءة للمستخدم الحالي.
    """
    count = Notification.unread_count_for(request.user)
    return JsonResponse({"count": count})

@login_required
@require_GET
def api_recent(request):
    """
    API: ترجع آخر 10 إشعارات للمستخدم الحالي (مقروءة وغير مقروءة).
    """
    qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")[:10]
    data = [{
        "id": n.id,
        "title": n.title or "تنبيه جديد",
        "body": n.body or "",
        "is_read": n.is_read,
        "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
        "url": n.get_absolute_url(),
    } for n in qs]
    return JsonResponse({"items": data})

@login_required
@require_POST
def api_mark_read(request: HttpRequest, pk: int) -> JsonResponse:
    """
    API: تعليم تنبيه محدّد كمقروء (للمالك فقط).
    """
    n = get_object_or_404(Notification, pk=pk)
    if n.recipient_id != request.user.id:
        return JsonResponse({"ok": False, "detail": "غير مسموح"}, status=403)
    if not n.is_read:
        n.mark_read(save=True)
    return JsonResponse({"ok": True})
