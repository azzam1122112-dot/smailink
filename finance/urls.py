# finance/urls.py
from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "finance"

urlpatterns = [
    # ======================
    # لوحة المالية
    # ======================

    # الاسم المعياري الجديد
    path("", views.finance_home, name="finance_home"),

    # Aliases قديمة محولة إلى الاسم الجديد (توافق خلفي)
    path("home/", RedirectView.as_view(pattern_name="finance:finance_home", permanent=False), name="home"),
    path("index/", RedirectView.as_view(pattern_name="finance:finance_home", permanent=False), name="index"),
    path("dashboard/", RedirectView.as_view(pattern_name="finance:finance_home", permanent=False), name="dashboard"),

    # ======================
    # إعدادات المالية (نِسَب العمولة والضريبة)
    # ======================
    path("settings/", views.settings_view, name="settings"),
    # Alias للتوافق مع قوالب/أكواد قديمة
    path("settings/save/", RedirectView.as_view(pattern_name="finance:settings", permanent=False), name="settings_save"),

    # ======================
    # قائمة الطلبات قيد التنفيذ
    # ======================
    path("in-progress/", views.inprogress_requests, name="in_progress"),
    # Aliases للاسم/المسار القديم
    path("inprogress/", RedirectView.as_view(pattern_name="finance:in_progress", permanent=False), name="inprogress"),
    path("requests/in-progress/", RedirectView.as_view(pattern_name="finance:in_progress", permanent=False), name="requests_in_progress"),

    # ======================
    # الفواتير
    # ======================
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/list/", RedirectView.as_view(pattern_name="finance:invoice_list", permanent=False), name="invoices_list"),  # alias
    path("invoice/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("inv/<int:pk>/", RedirectView.as_view(pattern_name="finance:invoice_detail", permanent=False), name="invoice"),  # alias مختصر

    # وسم كمدفوعة
    path("invoice/<int:pk>/mark-paid/", views.mark_invoice_paid, name="mark_invoice_paid"),
    path("invoice/mark-paid/<int:pk>/", RedirectView.as_view(pattern_name="finance:mark_invoice_paid", permanent=False), name="invoice_mark_paid"),  # alias

    # فواتير اتفاقية محددة (نمط الدفعة الواحدة)
    path("agreement/<int:agreement_id>/invoices/", views.agreement_invoices, name="agreement_invoices"),
    path("ag/<int:agreement_id>/invoices/", RedirectView.as_view(pattern_name="finance:agreement_invoices", permanent=False), name="ag_invoices"),  # alias

    # ======================
    # Checkout + تأكيد مرجع التحويل البنكي
    # ======================
    path("checkout/ag/<int:agreement_id>/", views.checkout_agreement, name="checkout_agreement"),
    path("checkout/confirm/<int:invoice_id>/", views.confirm_bank_transfer, name="confirm_bank_transfer"),
    # Aliases شائعة للتوافق
    path("invoice/<int:invoice_id>/confirm/", RedirectView.as_view(pattern_name="finance:confirm_bank_transfer", permanent=False), name="invoice_confirm"),
    path("confirm-transfer/<int:invoice_id>/", RedirectView.as_view(pattern_name="finance:confirm_bank_transfer", permanent=False), name="confirm_transfer"),

    # صفحة تشغيلية: تأكيد تحويلات العملاء (الفواتير غير المدفوعة التي لها paid_ref)
    path("confirm-transfers/", views.confirm_transfers, name="confirm_transfers"),
    path("confirm/", RedirectView.as_view(pattern_name="finance:confirm_transfers", permanent=False), name="confirm"),  # alias مختصر

    # ======================
    # تقارير ومدفوعات
    # ======================
    path("client/payments/", views.client_payments, name="client_payments"),
    # Aliases لأسماء قديمة محتملة
    path("payments/", RedirectView.as_view(pattern_name="finance:client_payments", permanent=False), name="payments"),
    path("my-payments/", RedirectView.as_view(pattern_name="finance:client_payments", permanent=False), name="my_payments"),

    path("employee/dues/", views.employee_dues, name="employee_dues"),
    path("my-dues/", RedirectView.as_view(pattern_name="finance:employee_dues", permanent=False), name="my_dues"),  # alias

    path("collections/", views.collections_report, name="collections_report"),
    path("collections/export.csv", views.export_invoices_csv, name="export_invoices_csv"),
    path("collections/export/", RedirectView.as_view(pattern_name="finance:export_invoices_csv", permanent=False), name="collections_export"),  # alias

    # ======================
    # Callback / Webhook من بوابة الدفع
    # ======================
    path("payment/callback/", views.payment_callback, name="payment_callback"),
    path("payment/webhook/", views.payment_webhook, name="payment_webhook"),

    # ======================
    # صرفيات الموظفين (Placeholder)
    # ======================
    path("payouts/", views.payouts_list, name="payouts_list"),
    # Aliases مساعدة
    path("employee/payouts/", RedirectView.as_view(pattern_name="finance:payouts_list", permanent=False), name="employee_payouts"),
]
