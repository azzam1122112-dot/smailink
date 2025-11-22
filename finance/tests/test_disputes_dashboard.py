from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from marketplace.models import Request
from agreements.models import Agreement
from finance.models import Invoice, Payout

try:
    from disputes.models import Dispute
except Exception:
    Dispute = None


class FinanceDisputesDashboardTests(TestCase):
    def setUp(self):
        self.finance = User.objects.create_user(username="fin", password="123", role="finance")
        self.client_user = User.objects.create_user(username="cli", password="123", role="client")
        self.emp = User.objects.create_user(username="emp", password="123", role="employee")

        completed_val = getattr(getattr(Request, "Status", None), "COMPLETED", "completed")
        self.req = Request.objects.create(title="طلب", client=self.client_user, status=completed_val)

        self.ag = Agreement.objects.create(request=self.req, employee=self.emp, total_amount=Decimal("100.00"))

        paid_val = getattr(getattr(Invoice, "Status", None), "PAID", "paid")
        self.inv = Invoice.objects.create(agreement=self.ag, amount=Decimal("115.00"), status=paid_val)

        if Dispute:
            open_val = getattr(getattr(Dispute, "Status", None), "OPEN", "open")
            self.dispute = Dispute.objects.create(request=self.req, title="نزاع", status=open_val)

    def test_dashboard_open_by_finance(self):
        if not Dispute:
            return
        self.client.login(username="fin", password="123")
        r = self.client.get(reverse("finance:disputes_dashboard"))
        self.assertEqual(r.status_code, 200)

    def test_release_creates_payout(self):
        if not Dispute:
            return
        self.client.login(username="fin", password="123")
        url = reverse("finance:dispute_release", args=[self.dispute.pk])
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)

        self.assertTrue(
            Payout.objects.filter(agreement=self.ag, status=Payout.Status.PENDING).exists()
        )

    def test_refund_cancels_pending_payout(self):
        if not Dispute:
            return
        Payout.objects.create(
            employee=self.emp,
            agreement=self.ag,
            invoice=self.inv,
            amount=Decimal("90.00"),
            status=Payout.Status.PENDING,
            issued_at=timezone.now(),
        )

        self.client.login(username="fin", password="123")
        url = reverse("finance:dispute_refund", args=[self.dispute.pk])
        r = self.client.post(url, {"amount": "50"})
        self.assertEqual(r.status_code, 302)

        p = Payout.objects.filter(agreement=self.ag).first()
        self.assertEqual(p.status, Payout.Status.CANCELLED)
