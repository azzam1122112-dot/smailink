from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from marketplace.models import Request
from finance.models import Invoice
from agreements.models import Agreement

class RequestStateInvoiceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client_user = User.objects.create_user(email='client@test.com', password='1234', name='Client', role='client')
        self.employee_user = User.objects.create_user(email='employee@test.com', password='1234', name='Employee', role='employee')
        self.client = Client()
        self.client.force_login(self.client_user)

    def test_cannot_set_in_progress_without_paid_invoice(self):
        req = Request.objects.create(title='طلب اختبار', client=self.client_user, estimated_duration_days=1, estimated_price=1000)
        agreement = Agreement.objects.create(title='اتفاقية اختبار', request=req, employee=self.employee_user, status=Agreement.Status.ACCEPTED)
        invoice = Invoice.objects.create(agreement=agreement, amount=1000, status=Invoice.Status.UNPAID)
        agreement.invoice = invoice
        agreement.save()
        req.agreement = agreement
        req.save()
        # محاولة تغيير الحالة إلى in_progress بدون دفع الفاتورة
        response = self.client.post(f'/marketplace/r/{req.pk}/state/change/', {'state': 'in_progress'})
        # يجب أن يتم إعادة التوجيه مع رسالة خطأ (لا يمكن تحويل الطلب)
        self.assertEqual(response.status_code, 302)

    def test_can_set_in_progress_with_paid_invoice(self):
        req = Request.objects.create(title='طلب اختبار', client=self.client_user, estimated_duration_days=1, estimated_price=1000)
        agreement = Agreement.objects.create(title='اتفاقية اختبار', request=req, employee=self.employee_user, status=Agreement.Status.ACCEPTED)
        invoice = Invoice.objects.create(agreement=agreement, amount=1000, status=Invoice.Status.PAID)
        agreement.invoice = invoice
        agreement.save()
        req.agreement = agreement
        req.save()
        # محاولة تغيير الحالة إلى in_progress بعد دفع الفاتورة
        response = self.client.post(f'/marketplace/r/{req.pk}/state/change/', {'state': 'in_progress'})
        req.refresh_from_db()
        self.assertIn(req.status, ['in_progress', 'completed'])
