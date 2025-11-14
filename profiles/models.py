from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.db.models.signals import post_save
from django.dispatch import receiver

User = settings.AUTH_USER_MODEL


# ====== مسارات رفع آمنة ======
def employee_upload(instance, filename: str) -> str:
    ts = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"employees/{instance.user_id}/{ts}_{filename}"


def portfolio_upload(instance, filename: str) -> str:
    ts = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"portfolio/{instance.owner_id}/{ts}_{filename}"


# ====== حالات KYC ======
class KYCStatus(models.TextChoices):
    NONE = "none", "بدون توثيق"
    PENDING = "pending", "قيد المراجعة"
    VERIFIED = "verified", "موثّق"
    REJECTED = "rejected", "مرفوض"


class EmployeeProfile(models.Model):
    """
    بروفايل التقني/الموظف:
    - بيانات عامة (title/specialty/city/skills/bio/photo).
    - تسعير وتقييم ومؤشرات أداء.
    - رؤية عامة + KYC مبسّط.
    - رابط واتساب عبر Proxy لإخفاء الرقم خارج المنصة.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="employee_profile")
    slug = models.SlugField(unique=True, max_length=180, editable=False)

    title = models.CharField("المسمى/اللقب المهني", max_length=120, blank=True)
    specialty = models.CharField("التخصص", max_length=120, blank=True)
    city = models.CharField("المدينة", max_length=120, blank=True)
    skills = models.CharField(
        "مهارات (CSV)",
        max_length=400,
        blank=True,
        help_text="اكتب المهارات مفصولة بفواصل: Django, REST, Tailwind",
    )
    bio = models.TextField("نبذة مختصرة", blank=True)
    photo = models.ImageField("صورة", upload_to=employee_upload, blank=True, null=True)

    # تسعير/تقييم
    hourly_rate = models.DecimalField(
        "سعر الساعة (اختياري)", max_digits=9, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    rating = models.DecimalField(
        "تقييم",
        max_digits=3,
        decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        default=0,
    )
    reviews_count = models.PositiveIntegerField("عدد التقييمات", default=0)

    # ظهور عام
    public_visible = models.BooleanField("ظهور عام", default=True)

    # KYC مبسّط
    kyc_status = models.CharField("حالة التوثيق", max_length=20, choices=KYCStatus.choices, default=KYCStatus.NONE)
    national_id_last4 = models.CharField("آخر 4 أرقام من الهوية (اختياري)", max_length=4, blank=True)
    kyc_verified_at = models.DateTimeField("تاريخ توثيق KYC", blank=True, null=True)

    # مؤشرات أداء
    completed_jobs = models.PositiveIntegerField("طلبات مكتملة", default=0)
    avg_response_minutes = models.PositiveIntegerField("متوسط زمن الاستجابة بالدقائق", default=0)
    client_satisfaction = models.DecimalField(
        "رضا العملاء (0–100)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "بروفايل موظف"
        verbose_name_plural = "بروفايلات الموظفين"
        indexes = [
            models.Index(fields=["public_visible", "rating"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["city"]),
            models.Index(fields=["kyc_status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        username = getattr(self.user, "name", None) or getattr(self.user, "email", "") or str(self.user_id)
        return f"{username} — {self.specialty or 'تقني'}"

    # ====== توليد Slug ثابت وآمن ======
    def _build_slug_base(self) -> str:
        base = (getattr(self.user, "name", None) or "").strip()
        if not base:
            email = getattr(self.user, "email", "")
            base = (email.split("@")[0] if email else f"emp-{self.user_id}").strip()
        return slugify(base, allow_unicode=True) or f"emp-{self.user_id}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if creating or not self.slug:
            candidate = self._build_slug_base()
            slug_val = candidate
            i = 2
            while EmployeeProfile.objects.filter(slug=slug_val).exclude(pk=self.pk).exists():
                slug_val = f"{candidate}-{i}"
                i += 1
            self.slug = slug_val

        # حماية: قص آخر 4 أرقام فقط
        if self.national_id_last4 and len(self.national_id_last4) > 4:
            self.national_id_last4 = self.national_id_last4[-4:]

        # ختم وقت التوثيق عند التحول إلى VERIFIED
        if self.kyc_status == KYCStatus.VERIFIED and not self.kyc_verified_at:
            self.kyc_verified_at = timezone.now()

        super().save(*args, **kwargs)

    # ====== خصائص مساعدة ======
    @property
    def skills_list(self) -> list[str]:
        return [s.strip() for s in (self.skills or "").split(",") if s.strip()]

    @property
    def whatsapp_proxy_url(self) -> str:
        # endpoint وسيط لإخفاء الرقم — الفيو يطبّق RBAC/Rate-limit
        return reverse("profiles:whatsapp_redirect", args=[self.user_id])

    def get_absolute_url(self) -> str:
        return reverse("profiles:employee_detail", kwargs={"slug": self.slug})

    # ====== تحديث المقاييس من أنظمة أخرى ======
    def recalc_metrics(
        self,
        *,
        rating_avg: float | None = None,
        reviews_count: int | None = None,
        completed_jobs: int | None = None,
        avg_response_minutes: int | None = None,
        client_satisfaction: float | None = None,
    ) -> None:
        changed = False
        if rating_avg is not None:
            self.rating = max(0, min(5, float(rating_avg)))
            changed = True
        if reviews_count is not None:
            self.reviews_count = max(0, int(reviews_count))
            changed = True
        if completed_jobs is not None:
            self.completed_jobs = max(0, int(completed_jobs))
            changed = True
        if avg_response_minutes is not None:
            self.avg_response_minutes = max(0, int(avg_response_minutes))
            changed = True
        if client_satisfaction is not None:
            self.client_satisfaction = max(0, min(100, float(client_satisfaction)))
            changed = True
        if changed:
            self.save(update_fields=[
                "rating", "reviews_count", "completed_jobs",
                "avg_response_minutes", "client_satisfaction", "updated_at"
            ])


class PortfolioItem(models.Model):
    """
    عنصر من معرض الأعمال (صورة/ملف/رابط) يُعرض على البروفايل العام عند is_public=True.
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portfolio_items")
    title = models.CharField("العنوان", max_length=160)
    description = models.TextField("الوصف", blank=True)
    tags = models.CharField("وسوم (CSV)", max_length=240, blank=True)
    link = models.URLField("رابط خارجي (اختياري)", blank=True)
    image = models.ImageField("صورة العرض (اختياري)", upload_to=portfolio_upload, blank=True, null=True)
    attachment = models.FileField("ملف (اختياري)", upload_to=portfolio_upload, blank=True, null=True)

    is_public = models.BooleanField("ظهور عام", default=True)
    sort_order = models.PositiveIntegerField("ترتيب", default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "عنصر معرض أعمال"
        verbose_name_plural = "عناصر معرض الأعمال"
        ordering = ["sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "is_public"]),
            models.Index(fields=["sort_order"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.title} — {getattr(self.owner, 'name', '') or self.owner_id}"

    @property
    def tags_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]


# ====== إشارات: إنشاء بروفايل تلقائي لكل مستخدم جديد ======
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_employee_profile(sender, instance, created, **kwargs):  # pragma: no cover
    if created:
        with transaction.atomic():
            EmployeeProfile.objects.get_or_create(user=instance)
