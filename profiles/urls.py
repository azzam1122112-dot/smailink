from __future__ import annotations
from . import views

from django.urls import path
from django.views.generic.base import RedirectView

from .views import EmployeeListView, EmployeeDetailView, whatsapp_redirect

app_name = "profiles"

urlpatterns = [
    # القوائم
    path("", EmployeeListView.as_view(), name="employees_list"),
    path("techs/", RedirectView.as_view(pattern_name="profiles:employees_list", permanent=True), name="techs_list"),
    path("employees/", RedirectView.as_view(pattern_name="profiles:employees_list", permanent=True), name="employees_list_alias"),
    path('employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee_detail'),

    # ملفات عامة (slug)
    path("<slug:slug>/", EmployeeDetailView.as_view(), name="employee_detail"),
    path("tech/<slug:slug>/", EmployeeDetailView.as_view(), name="tech_profile_detail"),

    # تحويل واتساب الآمن
    path("w/emp/<int:user_id>/", whatsapp_redirect, name="whatsapp_redirect"),
]
