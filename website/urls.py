# website/urls.py
from django.urls import path
from . import views

from .views import (
    HomeView, AboutView, ServicesView, ContactView, PrivacyView, TermsView
)

app_name = "website"

urlpatterns = [
    path("", views.home_view, name="home"),

    # ملاحظة: نوفّر اسمين لكل مسار (بالنَّيمسبيس وبدونه) لتمرير القوالب القديمة
    path("", HomeView.as_view(), name="home"),
    path("about/", AboutView.as_view(), name="about"),
    path("services/", ServicesView.as_view(), name="services"),
    path("contact/", ContactView.as_view(), name="contact"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
    path("terms/", TermsView.as_view(), name="terms"),
]
