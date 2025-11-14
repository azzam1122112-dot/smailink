# website/views.py
from django.shortcuts import render
from django.views.generic import TemplateView

from accounts.models import User  # تأكد أن المسار صحيح في مشروعك


class BasePageView(TemplateView):
    """
    View أساسي يضيف سياقًا موحّدًا لكل الصفحات العامة
    - page_slug: لتفعيل عنصر القائمة النشط في القالب
    - page_title: عنوان افتراضي يمكن استخدامه في <title> أو الهيدر
    """

    page_slug: str | None = None
    page_title: str | None = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # اسم الصفحة لاستخدامه في إبراز عنصر القائمة في النافبار
        ctx["page_slug"] = getattr(self, "page_slug", None)
        # عنوان الصفحة الافتراضي (يمكن تجاوزه من القالب)
        ctx["page_title"] = getattr(self, "page_title", None)

        # لو احتجنا لاحقاً نضيف سياق مشترك لكل الصفحات العامة
        return ctx


# =============== دالة مساعدة لسياق الصفحة الرئيسية ===============

def _get_home_context() -> dict:
    """
    يبني سياق الصفحة الرئيسية:
    - team_members: قائمة التقنيين/الموظفين المعتمدين للعرض في الهوم.
    - metrics: أرقام بسيطة تُعرض في الكروت العلوية.
    """

    # جلب التقنيين (يمكنك تعديل الفلتر حسب الأدوار عندك)
    team_members = (
        User.objects.filter(role__in=["employee", "tech"], is_active=True)
        .order_by("-id")[:12]
    )

    metrics = {
        "active_requests": 0,        # يمكن ربطها لاحقاً من موديل الطلبات
        "accepted_agreements": 0,    # يمكن ربطها من موديل الاتفاقيات
        "total_paid": 0,             # يمكن ربطها من فواتير المالية
        "employees_count": team_members.count(),
    }

    return {
        "team_members": team_members,
        "metrics": metrics,
    }


# الرئيسية (نسخة CBV)
class HomeView(BasePageView):
    template_name = "website/home.html"
    page_slug = "home"
    page_title = "الصفحة الرئيسية"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_get_home_context())
        return ctx


# حول المنصة
class AboutView(BasePageView):
    template_name = "website/about.html"
    page_slug = "about"
    page_title = "حول المنصة"


# الخدمات
class ServicesView(BasePageView):
    template_name = "website/services.html"
    page_slug = "services"
    page_title = "خدماتنا"


# اتصل بنا
class ContactView(BasePageView):
    template_name = "website/contact.html"
    page_slug = "contact"
    page_title = "اتصل بنا"


# الخصوصية
class PrivacyView(BasePageView):
    template_name = "website/privacy.html"
    page_slug = "privacy"
    page_title = "سياسة الخصوصية"


# الشروط والأحكام
class TermsView(BasePageView):
    template_name = "website/terms.html"
    page_slug = "terms"
    page_title = "الشروط والأحكام"


# =============== نسخة FBV للرئيسية (في حال كنت تستخدمها في urls.py) ===============

def home_view(request):
    """
    نسخة دالة من الصفحة الرئيسية.
    لو ملف urls.py مربوط على home_view، فهذه الدالة
    ستمرّر أيضاً team_members و metrics لنفس القالب.
    """
    context = {
        "page_slug": "home",
        "page_title": "الصفحة الرئيسية",
    }
    context.update(_get_home_context())
    return render(request, "website/home.html", context)
