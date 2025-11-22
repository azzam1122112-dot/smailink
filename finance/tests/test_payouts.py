from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from finance.models import Payout
from agreements.models import Agreement
from marketplace.models import Request


def _make_user(**kwargs):
    """
    إنشاء مستخدم متوافق مع أي نموذج User مخصص:
    - يدعم phone أو username أو email حسب الموجود
    - يدعم role إن كان موجودًا
    """
    User = get_user_model()

    data = {}
    # user identifier
    import random, string
    if User._meta.get_field(getattr(User, "USERNAME_FIELD", "username")).name == "phone":
        data["phone"] = kwargs.pop("phone", "055" + ''.join(random.choices(string.digits, k=7)))
    elif "username" in [f.name for f in User._meta.fields]:
        data["username"] = kwargs.pop("username", "u" + ''.join(random.choices(string.digits, k=4)))
    else:
        # always generate unique email
        rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        data["email"] = kwargs.pop("email", f"u{rand}@example.com")

    # optional fields
    if "name" in [f.name for f in User._meta.fields]:
        data["name"] = kwargs.pop("name", data.get("username", "User"))
    if "role" in [f.name for f in User._meta.fields]:
        data["role"] = kwargs.pop("role", "client")

    data.update(kwargs)

    # create_user signature varies, so pass **data
    return User.objects.create_user(password="123", **data)


class PayoutsTests(TestCase):
    def setUp(self):
        self.finance = _make_user(phone="0551111111", role="finance", name="Finance")
        self.client_user = _make_user(phone="0552222222", role="client", name="Client")
        self.emp = _make_user(phone="0553333333", role="employee", name="Employee")

        completed_val = getattr(getattr(Request, "Status", None), "COMPLETED", "completed")

        self.req = Request.objects.create(
            title="طلب مكتمل",
            client=self.client_user,
            status=completed_val,
        )

        self.ag = Agreement.objects.create(
            request=self.req,
            employee=self.emp,
            total_amount=Decimal("100.00"),
            title="اتفاقية اختبار"
        )

        self.payout = Payout.objects.create(
            employee=self.emp,
            agreement=self.ag,
            amount=Decimal("90.00"),
            status=Payout.Status.PENDING,
            issued_at=timezone.now(),
        )

    def test_finance_can_open_payouts_list(self):
        self.client.force_login(self.finance)
        r = self.client.get(reverse("finance:payouts_list"))
        self.assertEqual(r.status_code, 200)

    def test_non_finance_blocked(self):
        self.client.force_login(self.client_user)
        r = self.client.get(reverse("finance:payouts_list"))
        self.assertEqual(r.status_code, 302)

    def test_mark_payout_paid(self):
        self.client.force_login(self.finance)
        url = reverse("finance:mark_payout_paid", args=[self.payout.pk])
        r = self.client.post(url, {"method": "bank", "ref_code": "TX123"})
        self.assertEqual(r.status_code, 302)

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, Payout.Status.PAID)
        self.assertEqual(self.payout.method, "bank")
        self.assertEqual(self.payout.ref_code, "TX123")
        self.assertIsNotNone(self.payout.paid_at)
