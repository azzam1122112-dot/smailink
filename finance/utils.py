# finance/utils.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Tuple, Optional, Iterable, Dict, Any
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import FinanceSettings

# ============================
# مفاتيح الكاش وإعداداته
# ============================
_FINANCE_CFG_CACHE_KEY = "finance:cfg:v2"  # v2 لتفريقه عن الإصدارات السابقة
_FINANCE_CFG_TTL = getattr(settings, "FINANCE_CFG_TTL", 600)  # 10 دقائق افتراضيًا


# ============================
# محولات وتنسيقات آمنة
# ============================
def _to_dec(val, q: Optional[str] = None) -> Decimal:
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


def money_q2(val) -> Decimal:
    """تقريب مبالغ نقدية إلى خانتين."""
    return _to_dec(val, "0.01")


def percent_q4(val) -> Decimal:
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
    fee = percent_q4(cfg.platform_fee_percent)
    vat = percent_q4(cfg.vat_rate)
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
    مفيد عندما لا تريد استدعاء FinanceSettings.current_rates مباشرة.
    """
    cfg = get_finance_cfg()
    return cfg.platform_fee_percent, cfg.vat_rate


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
    """
    يرجع إعدادات الحساب البنكي من settings مع قيم افتراضية آمنة للعرض.
    تُستخدم في صفحات checkout/الفواتير.
    """
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
# فترات التقارير (ملائمة للقوالب)
# ============================
def parse_period_params(period: str | None, from_str: str | None, to_str: str | None) -> Tuple[Optional[date], Optional[date]]:
    """
    يحوّل مُدخلات الفترة إلى (d1, d2) تاريخين شامِلَين:
    period: today | 7d | 30d | custom
    إذا custom: يعتمد from/to بصيغة YYYY-MM-DD (قد يكون أيًّا منهما فارغًا).
    الافتراضي: آخر 30 يومًا.
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
    # default
    return today - timedelta(days=29), today


# ============================
# تجميعات منسّقة للفواتير
# ============================
def _invoice_status_values() -> Dict[str, str]:
    """
    إرجاع قيم حالات الفاتورة من نموذج Invoice دون استيراد على المستوى العلوي
    (تفادي الدوائر). الاستيراد يتم داخل الدالة.
    """
    from .models import Invoice  # استيراد كسول
    return {
        "PAID": getattr(Invoice.Status, "PAID", "paid"),
        "UNPAID": getattr(Invoice.Status, "UNPAID", "unpaid"),
        "CANCELLED": getattr(Invoice.Status, "CANCELLED", "cancelled"),
    }


def invoices_totals(qs) -> Dict[str, Decimal]:
    """
    يحسب مجاميع أساسية على QuerySet للفواتير:
    - total: مجموع amount
    - paid: مجموع amount للحالة مدفوعة
    - unpaid: مجموع amount لغير المدفوعة
    - vat_total: مجموع VAT لكل الفواتير
    - fee_total: مجموع عمولة المنصّة لكل الفواتير
    ملاحظة: يعتمد الحقول الافتراضية (amount / vat_amount / platform_fee_amount).
    """
    from django.db.models import Q, Sum  # محلي
    st = _invoice_status_values()
    agg = qs.aggregate(
        total=Sum("amount"),
        paid=Sum("amount", filter=Q(status=st["PAID"])),
        unpaid=Sum("amount", filter=Q(status=st["UNPAID"])),
        vat_total=Sum("vat_amount"),
        fee_total=Sum("platform_fee_amount"),
    )
    return {
        "total": agg["total"] or Decimal("0.00"),
        "paid": agg["paid"] or Decimal("0.00"),
        "unpaid": agg["unpaid"] or Decimal("0.00"),
        "vat_total": agg["vat_total"] or Decimal("0.00"),
        "fee_total": agg["fee_total"] or Decimal("0.00"),
    }


def employee_net_from_invoices(qs) -> Decimal:
    """
    صافي الموظف = مجموع P (amount) - مجموع عمولة المنصّة (platform_fee_amount)
    على مجموعة فواتير معينة (قد تكون مُرشّحة مسبقاً حسب الموظف/الحالة).
    """
    from django.db.models import Sum  # محلي
    agg = qs.aggregate(p=Sum("amount"), fee=Sum("platform_fee_amount"))
    P = agg["p"] or Decimal("0.00")
    F = agg["fee"] or Decimal("0.00")
    return (P - F) if P >= F else Decimal("0.00")


def invoice_eff_date(inv) -> Optional[timezone.datetime]:
    """eff_date: تاريخ احتساب للتقارير (paid_at أو issued_at)."""
    paid_at = getattr(inv, "paid_at", None)
    if paid_at:
        return paid_at
    return getattr(inv, "issued_at", None)


# ============================
# Webhook: توقيع HMAC (اختياري)
# ============================
def verify_webhook_signature(body: bytes, header_signature: str, secret: Optional[str]) -> bool:
    """
    يتحقق من HMAC-SHA256 للـ body باستخدام secret.
    يعيد True إذا تطابق التوقيع مع الهيدر 'X-Payment-Signature'.
    """
    if not secret:
        return False
    try:
        import hmac, hashlib  # محلي لتجنّب الاستيراد غير اللازم
        calc = hmac.new(secret.encode("utf-8"), body or b"", hashlib.sha256).hexdigest()
        # استخدام compare_digest للحماية من التوقيت
        return hmac.compare_digest((header_signature or ""), calc)
    except Exception:
        return False
