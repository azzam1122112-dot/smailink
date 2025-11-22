from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User  # أو Teacher/Account حسب مشروعك
from finance.models import Invoice, Refund, FinanceSettings
from agreements.models import Agreement
from marketplace.models import Request


class RefundsTests(TestCase):
    def setUp(self):
        self.finance = User.objects.create_user(username="fin", password="123", role="finance")
        self.client_user = User.objects.create_user(username="cli", password="123", role="client")
        self.emp = User.objects.create_user(username="emp", password="123", role="employee")

        self.req = Request.objects.create(
            title="طلب اختبار",
            client=self.client_user,
            status=getattr(getattr(Request, "Status", None), "CANCELLED", "cancelled"),
        )
        self.ag = Agreement.objects.create(request=self.req, employee=self.emp, total_amount=Decimal("100.00"))

        self.inv = Invoice.objects.create(
            agreement=self.ag,
            amount=Decimal("100.00"),
            total_amount=Decimal("115.00"),
            status=getattr(getattr(Invoice, "Status", None), "PAID", "paid"),
            issued_at=timezone.now(),
            paid_at=timezone.now(),
        )

    def test_finance_can_open_dashboard(self):
        self.client.login(username="fin", password="123")
        r = self.client.get(reverse("finance:refunds_dashboard"))
        self.assertEqual(r.status_code, 200)

    def test_create_refund_partial(self):
        self.client.login(username="fin", password="123")
        url = reverse("finance:refund_create", args=[self.inv.pk])
        r = self.client.post(url, {"amount": "50.00", "reason": "اختبار"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Refund.objects.count(), 1)
        rf = Refund.objects.first()
        self.assertEqual(rf.amount, Decimal("50.00"))

    def test_cannot_refund_more_than_left(self):
        self.client.login(username="fin", password="123")
        url = reverse("finance:refund_create", args=[self.inv.pk])
        r = self.client.post(url, {"amount": "999.00"})
        self.assertEqual(Refund.objects.count(), 0)
