# finance/utils.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Tuple, Optional, Dict, Any
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import FinanceSettings


# ============================
# مفاتيح الكاش وإعداداته
# ============================
_FINANCE_CFG_CACHE_KEY = "finance:cfg:v3"  # v3 لتفريقه عن الإصدارات السابقة
_FINANCE_CFG_TTL = getattr(settings, "FINANCE_CFG_TTL", 600)  # 10 دقائق افتراضيًا


# ============================
# محولات وتنسيقات آمنة
# ============================
def _to_dec(val: Any, q: Optional[str] = None) -> Decimal:
    """تحويل آمن إلى Decimal مع تقريب اختياري."""
    if isinstance(val, Decimal):
        d = val
    else:
        try:
            d = Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            d = Decimal("0")

    if q:
        return d.quantize(Decimal(q), rounding=ROUND_HALF_UP)
    return d


def money_q2(val: Any) -> Decimal:
    """تقريب مبالغ نقدية إلى خانتين."""
    return _to_dec(val, "0.01")


def percent_q4(val: Any) -> Decimal:
    """تقريب نسب إلى أربع خانات (0..1)."""
    return _to_dec(val, "0.0001")


def fmt_money(val: Any) -> str:
    """تنسيق مبلغ نقدي كسلسلة بخانتين (للعرض و CSV)."""
    return f"{money_q2(val)}"


def fmt_percent01_to_pct(val01: Any) -> str:
    """
    تنسيق نسبة على مقياس 0..1 إلى نص % بخانتين.
    مثال: 0.15 -> '15.00%'.
    """
    v = _to_dec(val01)
    return f"{(v * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


# ============================
# إعدادات المالية (كاش)
# ============================
@dataclass(frozen=True)
class FinanceCfg:
    platform_fee_percent: Decimal  # 0..1
    vat_rate: Decimal              # 0..1
    updated_at: Optional[timezone.datetime]


def _fetch_cfg_from_db() -> FinanceCfg:
    """يجلب الإعدادات من قاعدة البيانات مع سقوط آمن لقيم افتراضية."""
    cfg = FinanceSettings.get_solo()
    fee = percent_q4(getattr(cfg, "platform_fee_percent", 0))
    vat = percent_q4(getattr(cfg, "vat_rate", 0))
    return FinanceCfg(
        platform_fee_percent=fee,
        vat_rate=vat,
        updated_at=getattr(cfg, "updated_at", None),
    )


def get_finance_cfg(force: bool = False) -> FinanceCfg:
    """
    يُرجع إعدادات المالية من الكاش أو من قاعدة البيانات.
    استخدم force=True لتجاوز الكاش.
    """
    if not force:
        cached = cache.get(_FINANCE_CFG_CACHE_KEY)
        if isinstance(cached, dict) and "platform_fee_percent" in cached and "vat_rate" in cached:
            return FinanceCfg(
                platform_fee_percent=_to_dec(cached["platform_fee_percent"], "0.0001"),
                vat_rate=_to_dec(cached["vat_rate"], "0.0001"),
                updated_at=cached.get("updated_at"),
            )

    cfg = _fetch_cfg_from_db()
    cache.set(
        _FINANCE_CFG_CACHE_KEY,
        {
            "platform_fee_percent": str(cfg.platform_fee_percent),
            "vat_rate": str(cfg.vat_rate),
            "updated_at": cfg.updated_at,
        },
        timeout=_FINANCE_CFG_TTL,
    )
    return cfg


def invalidate_finance_cfg_cache() -> None:
    """يمسح كاش إعدادات المالية — استدعِه بعد أي تعديل على FinanceSettings."""
    cache.delete(_FINANCE_CFG_CACHE_KEY)


def current_rates_cached() -> Tuple[Decimal, Decimal]:
    """
    يُرجع (platform_fee_percent, vat_rate) من الكاش/القاعدة.
    """
    cfg = get_finance_cfg()
    return cfg.platform_fee_percent, cfg.vat_rate


# ============================
# حساب الصافي والإجمالي حسب السياسة المعتمدة
# ============================
def calculate_financials_from_net(
    net_amount: Any,
    platform_fee_percent: Optional[Any] = None,
    vat_rate: Optional[Any] = None,
) -> Dict[str, Decimal]:
    """
    السياسة المعتمدة في SamiLink:

    - العميل لا يتحمّل نسبة المنصّة.
    - العميل يدفع: P + (P * VAT)
    - صافي الموظف: P - (P * Fee)
    - العمولة تُخصم من الموظف فقط.

    المدخل:
      - net_amount: السعر المقترح P (في العروض/الفواتير)
      - platform_fee_percent: نسبة عمولة المنصّة (0..1) مثال 0.10
      - vat_rate: نسبة الضريبة (0..1) مثال 0.15

    إذا لم تُمرَّر النسب، يتم جلبها من FinanceSettings عبر الكاش.

    المخرجات:
      - net_for_employee: صافي الموظف بعد خصم العمولة
      - platform_fee: قيمة عمولة المنصّة (تخصم من الموظف)
      - vat_amount: قيمة الضريبة على السعر المقترح فقط
      - client_total: المبلغ الذي يدفعه العميل (السعر + الضريبة فقط)
    """
    P = money_q2(net_amount)

    # fallback للإعدادات إذا لم تُمرَّر النسب
    if platform_fee_percent is None or vat_rate is None:
        cfg = get_finance_cfg()
        if platform_fee_percent is None:
            platform_fee_percent = cfg.platform_fee_percent
        if vat_rate is None:
            vat_rate = cfg.vat_rate

    fee_p = percent_q4(platform_fee_percent)  # 0..1
    vat_p = percent_q4(vat_rate)              # 0..1

    if P <= Decimal("0.00"):
        return {
            "net_for_employee": Decimal("0.00"),
            "platform_fee": Decimal("0.00"),
            "vat_amount": Decimal("0.00"),
            "client_total": Decimal("0.00"),
        }

    platform_fee = money_q2(P * fee_p)
    vat_amount = money_q2(P * vat_p)
    client_total = money_q2(P + vat_amount)
    net_for_employee = money_q2(P - platform_fee)

    return {
        "net_for_employee": net_for_employee,
        "platform_fee": platform_fee,
        "vat_amount": vat_amount,
        "client_total": client_total,
    }


def calculate_financials(
    net_amount: Any,
    platform_fee_percent: Optional[Any] = None,
    vat_rate: Optional[Any] = None,
) -> Dict[str, Decimal]:
    """Alias للتوافق الخلفي."""
    return calculate_financials_from_net(
        net_amount=net_amount,
        platform_fee_percent=platform_fee_percent,
        vat_rate=vat_rate,
    )


# ============================
# أدوات البنك/الدفع للعرض
# ============================
def mask_iban(iban: str) -> str:
    """إخفاء IBAN للعرض فقط."""
    s = "".join(ch for ch in (iban or "") if ch.isalnum())
    if len(s) <= 8:
        return iban or ""
    return f"{s[:4]} **** **** **** {s[-4:]}"


def get_bank_config() -> Dict[str, str]:
    """يرجع إعدادات الحساب البنكي من settings مع قيم افتراضية آمنة للعرض."""
    bank_name = getattr(settings, "BANK_NAME", "SAUDI BANK")
    bank_acc_name = getattr(settings, "BANK_ACCOUNT_NAME", "SamiLink LLC")
    bank_iban = getattr(settings, "BANK_IBAN", "SA00 0000 0000 0000 0000 0000")
    return {
        "BANK_NAME": bank_name,
        "BANK_ACCOUNT_NAME": bank_acc_name,
        "BANK_IBAN": bank_iban,
        "BANK_IBAN_MASKED": mask_iban(bank_iban),
    }


# ============================
# فترات التقارير
# ============================
def parse_period_params(
    period: str | None,
    from_str: str | None,
    to_str: str | None
) -> Tuple[Optional[date], Optional[date]]:
    """
    يحوّل مُدخلات الفترة إلى (d1, d2) تاريخين شامِلَين:
    period: today | 7d | 30d | custom
    """
    p = (period or "").strip()
    today = date.today()

    if p == "today":
        return today, today
    if p == "7d":
        return today - timedelta(days=6), today
    if p == "30d":
        return today - timedelta(days=29), today

    if p == "custom":
        try:
            d1 = date.fromisoformat((from_str or "").strip()) if from_str else None
        except Exception:
            d1 = None
        try:
            d2 = date.fromisoformat((to_str or "").strip()) if to_str else None
        except Exception:
            d2 = None
        return d1, d2

    return today - timedelta(days=29), today


# ============================
# تجميعات منسّقة للفواتير
# ============================
def _invoice_status_values() -> Dict[str, str]:
    """إرجاع قيم حالات الفاتورة من نموذج Invoice دون استيراد على المستوى العلوي."""
    from .models import Invoice
    return {
        "PAID": getattr(Invoice.Status, "PAID", "paid"),
        "UNPAID": getattr(Invoice.Status, "UNPAID", "unpaid"),
        "CANCELLED": getattr(Invoice.Status, "CANCELLED", "cancelled"),
    }


def invoices_totals(qs) -> Dict[str, Decimal]:
    """
    يحسب مجاميع أساسية على QuerySet للفواتير اعتمادًا على الحقول المخزنة.
    ملاحظة: بعض الفواتير القديمة قد تكون حقولها صفر.
    """
    from django.db.models import Q, Sum
    st = _invoice_status_values()
    agg = qs.aggregate(
        total=Sum("amount"),
        paid=Sum("amount", filter=Q(status=st["PAID"])),
        unpaid=Sum("amount", filter=Q(status=st["UNPAID"])),
        vat_total=Sum("vat_amount"),
        fee_total=Sum("platform_fee_amount"),
        client_total=Sum("total_amount"),
    )
    return {
        "total": agg["total"] or Decimal("0.00"),
        "paid": agg["paid"] or Decimal("0.00"),
        "unpaid": agg["unpaid"] or Decimal("0.00"),
        "vat_total": agg["vat_total"] or Decimal("0.00"),
        "fee_total": agg["fee_total"] or Decimal("0.00"),
        "client_total": agg["client_total"] or Decimal("0.00"),
    }


def invoices_totals_live(
    qs,
    platform_fee_percent: Optional[Any] = None,
    vat_rate: Optional[Any] = None
) -> Dict[str, Decimal]:
    """
    تجميعات "Live" تُحسب من amount مباشرة حسب السياسة المعتمدة،
    مفيدة لو حقول vat_amount / platform_fee_amount في الفواتير القديمة غير محدثة.
    """
    from django.db.models import Q, Sum, F, Value, DecimalField, ExpressionWrapper
    st = _invoice_status_values()

    if platform_fee_percent is None or vat_rate is None:
        cfg = get_finance_cfg()
        if platform_fee_percent is None:
            platform_fee_percent = cfg.platform_fee_percent
        if vat_rate is None:
            vat_rate = cfg.vat_rate

    fee_p = percent_q4(platform_fee_percent)
    vat_p = percent_q4(vat_rate)

    fee_expr = ExpressionWrapper(
        F("amount") * Value(fee_p),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    vat_expr = ExpressionWrapper(
        F("amount") * Value(vat_p),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    client_expr = ExpressionWrapper(
        F("amount") + vat_expr,
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    net_expr = ExpressionWrapper(
        F("amount") - fee_expr,
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )

    agg = qs.aggregate(
        total=Sum("amount"),
        paid=Sum("amount", filter=Q(status=st["PAID"])),
        unpaid=Sum("amount", filter=Q(status=st["UNPAID"])),
        vat_total=Sum(vat_expr),
        fee_total=Sum(fee_expr),
        client_total=Sum(client_expr),
        net_total=Sum(net_expr),
    )

    return {
        "total": agg["total"] or Decimal("0.00"),
        "paid": agg["paid"] or Decimal("0.00"),
        "unpaid": agg["unpaid"] or Decimal("0.00"),
        "vat_total": agg["vat_total"] or Decimal("0.00"),
        "fee_total": agg["fee_total"] or Decimal("0.00"),
        "client_total": agg["client_total"] or Decimal("0.00"),
        "net_total": agg["net_total"] or Decimal("0.00"),
    }


def employee_net_from_invoices(qs) -> Decimal:
    """صافي الموظف = مجموع P - مجموع عمولة المنصّة."""
    from django.db.models import Sum
    agg = qs.aggregate(p=Sum("amount"), fee=Sum("platform_fee_amount"))
    P = agg["p"] or Decimal("0.00")
    F = agg["fee"] or Decimal("0.00")
    return money_q2(P - F) if P >= F else Decimal("0.00")


def employee_net_from_invoices_live(qs, platform_fee_percent: Optional[Any] = None) -> Decimal:
    """صافي الموظف "Live" من amount مباشرة."""
    from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper

    if platform_fee_percent is None:
        platform_fee_percent = get_finance_cfg().platform_fee_percent

    fee_p = percent_q4(platform_fee_percent)
    net_expr = ExpressionWrapper(
        F("amount") - (F("amount") * Value(fee_p)),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    agg = qs.aggregate(net=Sum(net_expr))
    return agg["net"] or Decimal("0.00")


def invoice_eff_date(inv) -> Optional[timezone.datetime]:
    """eff_date: تاريخ احتساب للتقارير (paid_at أو issued_at)."""
    paid_at = getattr(inv, "paid_at", None)
    if paid_at:
        return paid_at
    return getattr(inv, "issued_at", None)


# ============================
# دفتر الحركة (Ledger) + الخزينة
# ============================
def record_ledger(
    entry_type: str,
    direction: str,
    amount: Any,
    *,
    invoice=None,
    payout=None,
    refund=None,
    tax_remittance=None,
    created_by=None,
    note: str = "",
):
    """
    Helper موحّد لإضافة قيد خزينة بشكل آمن.
    يستخدم lazy import لتجنّب circular imports.
    """
    from .models import LedgerEntry  # lazy

    amt = money_q2(amount)
    if amt <= Decimal("0.00"):
        return None

    # توحيد القيم إن أمكن
    if hasattr(LedgerEntry, "Type"):
        valid_types = {c.value for c in LedgerEntry.Type}
        if entry_type not in valid_types:
            entry_type = LedgerEntry.Type.CLIENT_PAYMENT

    if hasattr(LedgerEntry, "Direction"):
        valid_dirs = {c.value for c in LedgerEntry.Direction}
        if direction not in valid_dirs:
            direction = LedgerEntry.Direction.IN_

    return LedgerEntry.objects.create(
        entry_type=entry_type,
        direction=direction,
        amount=amt,
        invoice=invoice,
        payout=payout,
        refund=refund,
        tax_remittance=tax_remittance,
        created_by=created_by,
        note=(note or "")[:255],
    )


def treasury_balance() -> Decimal:
    """رصيد الخزينة اللحظي = مجموع الدخول - مجموع الخروج (من الـLedger)."""
    try:
        from django.db.models import Sum, Q
        from .models import LedgerEntry  # lazy

        agg = LedgerEntry.objects.aggregate(
            ins=Sum("amount", filter=Q(direction=LedgerEntry.Direction.IN_)),
            outs=Sum("amount", filter=Q(direction=LedgerEntry.Direction.OUT)),
        )
        ins = agg["ins"] or Decimal("0.00")
        outs = agg["outs"] or Decimal("0.00")
        return money_q2(ins - outs)
    except Exception:
        # سقوط آمن لو الجدول غير موجود أو لم يُفعّل بعد
        return Decimal("0.00")


def vat_stock() -> Decimal:
    """مخزون VAT الحالي = VAT محصّل من العملاء (مدفوعة) - VAT مُورّدة."""
    from django.db.models import Sum
    from .models import Invoice, TaxRemittance  # lazy

    st = _invoice_status_values()
    paid_vat = (
        Invoice.objects.filter(status=st["PAID"])
        .aggregate(s=Sum("vat_amount"))["s"]
        or Decimal("0.00")
    )
    remitted = (
        TaxRemittance.objects
        .exclude(status=getattr(TaxRemittance.Status, "CANCELLED", "cancelled"))
        .aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )
    return money_q2(paid_vat - remitted)


def pending_employee_payable() -> Decimal:
    """إجمالي مستحقات الموظفين بانتظار الصرف (Pending Payouts)."""
    from django.db.models import Sum
    from .models import Payout  # lazy

    pending = (
        Payout.objects.filter(status=getattr(Payout.Status, "PENDING", "pending"))
        .aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )
    return money_q2(pending)


def customer_liability() -> Decimal:
    """التزامات العملاء = إجمالي ما دفعه العملاء - ما صُرف للموظفين - ما رُدّ للعملاء."""
    from django.db.models import Sum
    from .models import Invoice, Payout, Refund  # lazy

    st = _invoice_status_values()
    paid_invoices_total = (
        Invoice.objects.filter(status=st["PAID"])
        .aggregate(s=Sum("total_amount"))["s"]
        or Decimal("0.00")
    )
    paid_payouts_total = (
        Payout.objects.filter(status=getattr(Payout.Status, "PAID", "paid"))
        .aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )
    refunded_total = (
        Refund.objects.filter(status=getattr(Refund.Status, "SENT", "sent"))
        .aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )

    return money_q2(paid_invoices_total - paid_payouts_total - refunded_total)


def treasury_snapshot() -> Dict[str, Decimal]:
    """
    Snapshot جاهز للوحة المالية:
    - treasury_balance
    - customer_liability
    - pending_employee_payable
    - vat_stock
    """
    return {
        "treasury_balance": treasury_balance(),
        "customer_liability": customer_liability(),
        "pending_employee_payable": pending_employee_payable(),
        "vat_stock": vat_stock(),
    }


# ============================
# استحقاق صرف الموظف (Eligibility)
# ============================
@dataclass
class PayoutEligibility:
    ok: bool
    reason: str = ""


def is_eligible_for_payout(
    *,
    agreement=None,
    invoice=None,
    now=None,
    safety_days: int = 3,
) -> PayoutEligibility:
    """
    يقرر هل الموظف مستحق للصرف الآن.

    الشروط:
    1) الطلب مكتمل (completed).
    2) الفاتورة مدفوعة (paid) + لها paid_at.
    3) لا يوجد نزاع (disputed).
    4) مرّت نافذة الأمان safety_days بعد paid_at.
    5) لا يوجد أمر صرف سابق غير ملغي لنفس الاتفاقية/الفاتورة.
    """
    from finance.models import Payout
    from finance.models import Invoice
    from agreements.models import Agreement
    from marketplace.models import Request

    now = now or timezone.now()

    if invoice is None and agreement is None:
        return PayoutEligibility(False, "يلزم تمرير agreement أو invoice.")

    if invoice is None and agreement is not None:
        paid_val = getattr(getattr(Invoice, "Status", None), "PAID", "paid")
        invoice = (
            Invoice.objects
            .filter(agreement=agreement, status=paid_val)
            .order_by("-paid_at", "-issued_at", "-id")
            .first()
        )

    if agreement is None and invoice is not None:
        agreement = getattr(invoice, "agreement", None)

    if agreement is None:
        return PayoutEligibility(False, "الاتفاقية غير موجودة.")
    if invoice is None:
        return PayoutEligibility(False, "لا توجد فاتورة مدفوعة مرتبطة بالاتفاقية.")

    req = getattr(agreement, "request", None)
    if req is None:
        return PayoutEligibility(False, "الطلب غير مرتبط بالاتفاقية.")

    completed_req_val = getattr(getattr(Request, "Status", None), "COMPLETED", "completed")
    disputed_req_val = getattr(getattr(Request, "Status", None), "DISPUTED", "disputed")
    paid_inv_val = getattr(getattr(Invoice, "Status", None), "PAID", "paid")
    cancelled_payout_val = getattr(getattr(Payout, "Status", None), "CANCELLED", "cancelled")

    # 1) الطلب مكتمل
    if (getattr(req, "status", "") or "").lower() != str(completed_req_val).lower():
        return PayoutEligibility(False, "الطلب غير مكتمل بعد.")

    # 2) الفاتورة مدفوعة
    if (getattr(invoice, "status", "") or "").lower() != str(paid_inv_val).lower():
        return PayoutEligibility(False, "الفاتورة غير مدفوعة.")
    paid_at = getattr(invoice, "paid_at", None)
    if not paid_at:
        return PayoutEligibility(False, "تاريخ الدفع غير متوفر.")

    # 3) لا نزاع
    if (getattr(req, "status", "") or "").lower() == str(disputed_req_val).lower():
        return PayoutEligibility(False, "مجمّد بسبب نزاع على الطلب.")

    # 4) نافذة الأمان (قابلة للضبط مستقبلاً من FinanceSettings إن أضفت الحقل)
    try:
        cfg = FinanceSettings.get_solo()
        safety_days = int(getattr(cfg, "payout_safety_days", safety_days) or safety_days)
    except Exception:
        safety_days = safety_days

    ready_at = paid_at + timedelta(days=max(safety_days, 0))
    if now < ready_at:
        remaining = (ready_at - now).days + 1
        return PayoutEligibility(False, f"بانتظار نافذة الأمان ({remaining} يوم/أيام).")

    # 5) منع تكرار الصرف
    exists = (
        Payout.objects
        .filter(agreement=agreement)
        .exclude(status=cancelled_payout_val)
        .exists()
    )
    if exists:
        return PayoutEligibility(False, "تم إصدار أمر صرف سابق لهذه الاتفاقية.")

    return PayoutEligibility(True, "جاهز للصرف.")


# ============================
# Webhook: توقيع HMAC (اختياري)
# ============================
def verify_webhook_signature(
    body: bytes,
    header_signature: str,
    secret: Optional[str]
) -> bool:
    """يتحقق من HMAC-SHA256 للـ body باستخدام secret."""
    if not secret:
        return False
    try:
        import hmac, hashlib
        calc = hmac.new(secret.encode("utf-8"), body or b"", hashlib.sha256).hexdigest()
        return hmac.compare_digest((header_signature or ""), calc)
    except Exception:
        return False
