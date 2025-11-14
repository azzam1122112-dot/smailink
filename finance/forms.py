# finance/forms.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Tuple

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import FinanceSettings, Invoice, Payout


# =======================
# أدوات مساعدة رقمية
# =======================
def _as_decimal(val) -> Decimal:
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _q2(val: Decimal) -> Decimal:
    return _as_decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(val: Decimal) -> Decimal:
    return _as_decimal(val).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


# =======================
# إعدادات مالية عامة
# =======================
class FinanceSettingsForm(forms.ModelForm):
    """
    تحرير نسب المنصّة والـ VAT كنِسب بين 0..1 (0.10 = 10%، 0.15 = 15%).
    """
    platform_fee_percent = forms.DecimalField(
        label="نسبة عمولة المنصّة (0..1)",
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        decimal_places=4,
        max_digits=5,
        help_text="أدخل نسبة بين 0 و 1 (مثال: 0.10 = 10٪).",
    )
    vat_rate = forms.DecimalField(
        label="نسبة VAT (0..1)",
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        decimal_places=4,
        max_digits=5,
        help_text="أدخل نسبة بين 0 و 1 (مثال: 0.15 = 15٪).",
    )

    class Meta:
        model = FinanceSettings
        fields = ["platform_fee_percent", "vat_rate"]

    def clean_platform_fee_percent(self):
        v = _q4(self.cleaned_data["platform_fee_percent"])
        if not (Decimal("0") <= v <= Decimal("1")):
            raise ValidationError("النسبة يجب أن تكون بين 0 و 1.")
        return v

    def clean_vat_rate(self):
        v = _q4(self.cleaned_data["vat_rate"])
        if not (Decimal("0") <= v <= Decimal("1")):
            raise ValidationError("النسبة يجب أن تكون بين 0 و 1.")
        return v

    def save(self, commit: bool = True):
        obj: FinanceSettings = super().save(commit=False)
        obj.platform_fee_percent = _q4(obj.platform_fee_percent)
        obj.vat_rate = _q4(obj.vat_rate)
        if commit:
            obj.save()
        return obj


# =======================
# فلاتر القوائم والتقارير
# =======================
STATUS_FILTER_CHOICES = (
    ("all", "الكل"),
    ("unpaid", "غير مدفوعة"),
    ("paid", "مدفوعة"),
    ("cancelled", "ملغاة"),
)

PERIOD_CHOICES = (
    ("30d", "آخر 30 يومًا"),
    ("7d", "آخر 7 أيام"),
    ("today", "اليوم"),
    ("custom", "مخصّص"),
)


class InvoiceFilterForm(forms.Form):
    """
    فلتر قائمة الفواتير.
    ملاحظة: الفيوهات الحالية تقرأ القيم من request.GET مباشرة (status/method/q/from/to).
    نوفّر حقول from_date/to_date لتسهيل القوالب، مع دالة cleaned_range() لإخراج YYYY-MM-DD.
    """
    status = forms.ChoiceField(label="الحالة", choices=STATUS_FILTER_CHOICES, required=False, initial="all")
    method = forms.CharField(label="طريقة الدفع", required=False)
    q = forms.CharField(label="بحث", required=False, help_text="ID للطلب/الاتفاقية أو مرجع")
    from_date = forms.DateField(
        label="من تاريخ", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    to_date = forms.DateField(
        label="إلى تاريخ", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, **kwargs):
        """
        نقرأ قيم GET['from'] و GET['to'] لملء from_date/to_date إن تم تمريرها نصيًا.
        """
        super().__init__(*args, **kwargs)
        data = self.data or {}
        f = data.get("from")
        t = data.get("to")
        # لا نرمي استثناءً إن كانت قيم غير صالحة؛ الفيو يعالجها مباشرة
        if f and not self.data.get("from_date"):
            self.fields["from_date"].initial = f
        if t and not self.data.get("to_date"):
            self.fields["to_date"].initial = t

    def cleaned_range(self) -> Tuple[Optional[str], Optional[str]]:
        """ترجع (YYYY-MM-DD, YYYY-MM-DD)."""
        d1 = self.cleaned_data.get("from_date")
        d2 = self.cleaned_data.get("to_date")
        return (d1.isoformat() if d1 else None, d2.isoformat() if d2 else None)


class CollectionsReportFilterForm(forms.Form):
    """
    فلتر تقرير التحصيل. يتوافق مع الفيو:
    period | status | method | q | from | to
    """
    period = forms.ChoiceField(label="الفترة", choices=PERIOD_CHOICES, required=False, initial="30d")
    status = forms.ChoiceField(label="الحالة", choices=STATUS_FILTER_CHOICES, required=False, initial="all")
    method = forms.CharField(label="طريقة الدفع", required=False)
    q = forms.CharField(label="بحث", required=False)
    from_date = forms.DateField(label="من تاريخ", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    to_date = forms.DateField(label="إلى تاريخ", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        # عندما لا تكون الفترة مخصّصة، نتجاهل from/to
        if data.get("period") != "custom":
            data["from_date"] = None
            data["to_date"] = None
        return data

    def cleaned_range(self) -> Tuple[Optional[str], Optional[str]]:
        d1 = self.cleaned_data.get("from_date")
        d2 = self.cleaned_data.get("to_date")
        return (d1.isoformat() if d1 else None, d2.isoformat() if d2 else None)


# =======================
# فواتير: إجراءات الدفع
# =======================
class ConfirmBankTransferForm(forms.Form):
    """يسجّل العميل مرجع التحويل البنكي فقط (لا يوسم كمدفوع من هنا)."""
    paid_ref = forms.CharField(
        label="مرجع التحويل البنكي",
        min_length=4,
        max_length=64,
        help_text="أدخل رقم/مرجع التحويل البنكي (4 أحرف/أرقام على الأقل).",
    )

    def clean_paid_ref(self):
        ref = (self.cleaned_data["paid_ref"] or "").strip()
        if len(ref) < 4:
            raise ValidationError("المرجع قصير جدًا.")
        return ref


class InvoiceMarkPaidForm(forms.Form):
    """
    وسم الفاتورة كمدفوعة من المالية.
    لا تقوم بالحفظ؛ استعمل invoice.save() من داخل الفيو داخل transaction.
    """
    method = forms.CharField(label="طريقة السداد", required=False, max_length=50)
    ref_code = forms.CharField(label="مرجع العملية", required=False, max_length=100)
    paid_ref = forms.CharField(label="مرجع التحويل البنكي", required=False, max_length=64)
    paid_at = forms.DateTimeField(
        label="تاريخ السداد", required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"})
    )

    def apply(self, invoice: Invoice) -> Invoice:
        """تطبيق القيم على الفاتورة (بدون حفظ)."""
        method = (self.cleaned_data.get("method") or "").strip()
        ref_code = (self.cleaned_data.get("ref_code") or "").strip()
        paid_ref = (self.cleaned_data.get("paid_ref") or "").strip()
        paid_at = self.cleaned_data.get("paid_at")

        invoice.status = Invoice.Status.PAID
        if method:
            invoice.method = method[:50]
        if ref_code:
            invoice.ref_code = ref_code[:100]
        if paid_ref:
            invoice.paid_ref = paid_ref[:64]

        if paid_at:
            # تحويل datetime-local (naive) إلى aware حسب إعدادات المنطقة
            if timezone.is_naive(paid_at):
                paid_at = timezone.make_aware(paid_at, timezone.get_current_timezone())
            invoice.paid_at = paid_at
        elif invoice.paid_at is None:
            invoice.paid_at = timezone.now()

        # إعادة الاحتساب احتياطيًا
        invoice.recompute_totals()
        return invoice


# =======================
# أوامر صرف الموظف (Payouts)
# =======================
class PayoutCreateForm(forms.ModelForm):
    """
    إنشاء أمر صرف لموظف. يمكن ربطه باتفاقية/فاتورة اختياريًا.
    المبلغ يمثل الصافي للموظف بعد عمولة المنصّة.
    """
    amount = forms.DecimalField(label="المبلغ", decimal_places=2, max_digits=12, min_value=Decimal("0"))

    class Meta:
        model = Payout
        fields = ["employee", "agreement", "invoice", "amount", "method", "ref_code", "note"]

    def clean_amount(self):
        amt = _q2(self.cleaned_data["amount"])
        if amt < Decimal("0"):
            raise ValidationError("المبلغ لا يمكن أن يكون سالبًا.")
        return amt

    def clean(self):
        data = super().clean()
        agreement = data.get("agreement")
        invoice = data.get("invoice")

        # إن تم تمرير invoice، يجب أن تتبع نفس الاتفاقية إن وُجدت
        if invoice and agreement and invoice.agreement_id != agreement.id:
            raise ValidationError("الفاتورة المختارة لا تتبع الاتفاقية المحددة.")
        return data


class PayoutSetPaidForm(forms.Form):
    """
    وسم أمر الصرف كمدفوع (مالية).
    لا تحفظ مباشرة؛ استعمل save من الفيو داخل transaction.
    """
    method = forms.CharField(label="طريقة الصرف", required=False, max_length=50)
    ref_code = forms.CharField(label="مرجع العملية", required=False, max_length=100)
    paid_at = forms.DateTimeField(
        label="تاريخ الصرف", required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"})
    )

    def apply(self, payout: Payout) -> Payout:
        method = (self.cleaned_data.get("method") or "").strip()
        ref = (self.cleaned_data.get("ref_code") or "").strip()
        paid_at = self.cleaned_data.get("paid_at")

        payout.status = Payout.Status.PAID
        if method:
            payout.method = method[:50]
        if ref:
            payout.ref_code = ref[:100]

        if paid_at:
            if timezone.is_naive(paid_at):
                paid_at = timezone.make_aware(paid_at, timezone.get_current_timezone())
            payout.paid_at = paid_at
        elif payout.paid_at is None:
            payout.paid_at = timezone.now()

        return payout
