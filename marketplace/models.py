# marketplace/models.py
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Request(models.Model):
    """
    طلب خدمة ضمن دورة: NEW → OFFER_SELECTED → AGREEMENT_PENDING → IN_PROGRESS → (COMPLETED | DISPUTED | CANCELLED)

    ✦ اعتبارات أمان/جودة:
      - تحقق من الدور عند الإسناد (employee فقط).
      - تحقق من القيم الرقمية (مدة > 0، سعر ≥ 0) على مستوى الكود وعلى مستوى قاعدة البيانات.
      - جميع دوال تغيّر الحالة ذرّية (transaction.atomic).
      - خصائص قراءة مريحة للقوالب.
      - دوال مساعدة واضحة لتحديث SLA والانتقال بين الحالات.
    """

    class Status(models.TextChoices):
        NEW = "new", "طلب جديد"
        OFFER_SELECTED = "offer_selected", "تم اختيار عرض"
        AGREEMENT_PENDING = "agreement_pending", "اتفاقية بانتظار الموافقة"
        IN_PROGRESS = "in_progress", "قيد التنفيذ"
        COMPLETED = "completed", "مكتمل"
        DISPUTED = "disputed", "نزاع"          # توحيد التسمية
        CANCELLED = "cancelled", "ملغى"

    # ---- الصلات الرئيسية ----
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name="requests_as_client")
    assigned_employee = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="requests_as_employee", null=True, blank=True
    )

    # ---- بيانات الطلب ----
    title = models.CharField("العنوان", max_length=160)
    details = models.TextField("التفاصيل", blank=True)
    estimated_duration_days = models.PositiveIntegerField("مدة تقديرية (أيام)", default=7)
    estimated_price = models.DecimalField("سعر تقريبي", max_digits=12, decimal_places=2, default=0)
    links = models.TextField("روابط مرتبطة (اختياري)", blank=True)

    # ---- الحالة الموحدة ----
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NEW, db_index=True)

    # أعلام مساعدة (مشتقة منطقيًا غالبًا لكن تُحفظ للتوافق مع واجهات قديمة/التقارير)
    has_milestones = models.BooleanField(default=False)
    has_dispute = models.BooleanField(default=False)

    # --- SLA ---
    selected_at = models.DateTimeField(null=True, blank=True, db_index=True)  # وقت اختيار العرض
    agreement_due_at = models.DateTimeField("موعد استحقاق إرسال الاتفاقية", null=True, blank=True)
    sla_agreement_overdue = models.BooleanField("تجاوز مهلة إنشاء الاتفاقية (تم التنبيه؟)", default=False)

    # ---- طوابع زمنية ----
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # -------------------------
    # تحقق/سلامة بيانات
    # -------------------------
    def clean(self):
        # 1) الموظف المعيّن يجب أن يحمل الدور employee (إن كان موجودًا)
        if self.assigned_employee and getattr(self.assigned_employee, "role", None) != "employee":
            raise ValidationError("الإسناد يجب أن يكون إلى مستخدم بدور 'موظف'.")

        # 2) المدة التقديرية > 0
        if self.estimated_duration_days == 0:
            raise ValidationError("المدة التقديرية بالأيام يجب أن تكون أكبر من صفر.")

        # 3) السعر التقديري ≥ 0
        if self.estimated_price < 0:
            raise ValidationError("السعر التقديري لا يمكن أن يكون سالبًا.")

        # 4) اتساق الحالة مع النزاع
        if self.has_dispute and self.status != self.Status.DISPUTED:
            # لا نفرض هذه القاعدة بالقوة، نسمح بالتمييز، لكن ننبه منطقياً
            # يمكن تحويلها لرفع خطأ إذا رغبت:
            # raise ValidationError("عند has_dispute=True يجب أن تكون الحالة DISPUTED.")
            pass

        # 5) اتساق SLA: إن كانت agreement_due_at ماضية، علم التأخير يُحتمل
        if self.agreement_due_at and self.status == self.Status.AGREEMENT_PENDING:
            if timezone.now() > self.agreement_due_at and not self.sla_agreement_overdue:
                # لا نعدّل هنا (clean لا يجب أن يُغير الحالة)، فقط تحقق منطقي
                pass

    def save(self, *args, skip_clean: bool = False, **kwargs):
        """
        نحافظ على صحة البيانات باستدعاء full_clean() افتراضيًا قبل الحفظ.
        مرّر skip_clean=True عند الحاجة (داخل معاملات كبيرة) لتجنّب كلفة التحقق المتكرر.
        """
        if not skip_clean:
            self.full_clean()
        return super().save(*args, **kwargs)

    # -------------------------
    # خصائص قراءة مريحة للقوالب
    # -------------------------
    @property
    def agreement_overdue(self) -> bool:
        """هل تجاوزت الاتفاقية مهلة الإرسال/القرار؟"""
        return bool(self.agreement_due_at and timezone.now() > self.agreement_due_at)

    @property
    def is_new(self) -> bool: return self.status == self.Status.NEW

    @property
    def is_offer_selected(self) -> bool: return self.status == self.Status.OFFER_SELECTED

    @property
    def is_agreement_pending(self) -> bool: return self.status == self.Status.AGREEMENT_PENDING

    @property
    def is_in_progress(self) -> bool: return self.status == self.Status.IN_PROGRESS

    @property
    def is_completed(self) -> bool: return self.status == self.Status.COMPLETED

    @property
    def is_disputed(self) -> bool:
        # نبقي has_dispute داعمًا لتوافق الواجهات القديمة/الدوال
        return self.status == self.Status.DISPUTED or self.has_dispute

    @property
    def is_cancelled(self) -> bool: return self.status == self.Status.CANCELLED

    @property
    def selected_offer(self):
        """
        توافقًا مع أي كود قديم قد يستدعي 'selected' كنص خام.
        """
        # الاستيراد المتأخر لتفادي الحلقة المرجعية
        try:
            from .models import Offer  # type: ignore
            return (
                self.offers.select_related("employee")
                .filter(Q(status=Offer.Status.SELECTED) | Q(status="selected"))
                .first()
            )
        except Exception:
            # fallback آمن إن لم يتوفر Offer بعد
            return None

    # -------------------------
    # SLA/تحديثات اختيار العرض
    # -------------------------
    def mark_offer_selected_now(self, employee: User):
        """
        تحديثات موحّدة عند تحديد العرض/الإسناد (يضبط الـ SLA).
        تستدعى من view اختيار العرض (بداخل transaction.atomic).
        """
        if not employee or getattr(employee, "role", None) != "employee":
            raise ValidationError("لا يمكن الإسناد إلا لمستخدم بدور 'employee'.")

        now = timezone.now()
        self.assigned_employee = employee
        self.status = self.Status.OFFER_SELECTED
        self.offer_selected_at = now
        # المهلة الافتراضية لإرسال الاتفاقية: 3 أيام (حسب وثيقتك)
        self.agreement_due_at = now + timedelta(days=3)
        self.sla_agreement_overdue = False

    def flag_agreement_overdue_if_needed(self) -> bool:
        """
        يحدّث علم تأخّر الاتفاقية إن كانت المهلة تجاوزت.
        يعيد True إذا تمّ التحديث، وإلا False.
        """
        if self.status == self.Status.AGREEMENT_PENDING and self.agreement_overdue and not self.sla_agreement_overdue:
            self.sla_agreement_overdue = True
            self.save(update_fields=["sla_agreement_overdue", "updated_at"])
            return True
        return False

    # -------------------------
    # دوال المدير العام (admin-only) — تُستدعى من الفيوز
    # -------------------------
    @transaction.atomic
    def admin_cancel(self):
        """
        إلغاء الطلب: يفك الإسناد، يوقف الـ SLA، ويضع الحالة 'cancelled'.
        لا يحذف العروض أو الملاحظات (تبقى للأرشفة).
        """
        self.assigned_employee = None
        self.status = self.Status.CANCELLED
        self.offer_selected_at = None
        self.agreement_due_at = None
        self.sla_agreement_overdue = False
        self.save(update_fields=[
            "assigned_employee", "status", "offer_selected_at",
            "agreement_due_at", "sla_agreement_overdue", "updated_at"
        ])

    @transaction.atomic
    def reset_to_new(self):
        """
        إعادة الطلب إلى حالة NEW:
        - رفض جميع العروض الحالية (نبقيها في السجل للأرشفة).
        - إزالة الإسناد.
        - تصفير الـ SLA.
        - ضبط الحالة NEW.
        """
        # استيراد متأخر لتفادي الحلقة المرجعية داخل الملف
        try:
            from .models import Offer  # type: ignore
            (Offer.objects
                  .filter(request=self)
                  .exclude(status=getattr(Offer.Status, "REJECTED", "rejected"))
                  .update(status=getattr(Offer.Status, "REJECTED", "rejected")))
        except Exception:
            # إن لم يتوفر Offer لأي سبب، نتابع ما تبقى
            pass

        self.assigned_employee = None
        self.status = self.Status.NEW
        self.offer_selected_at = None
        self.agreement_due_at = None
        self.sla_agreement_overdue = False
        self.save(update_fields=[
            "assigned_employee", "status", "offer_selected_at",
            "agreement_due_at", "sla_agreement_overdue", "updated_at"
        ])

    @transaction.atomic
    def reassign_to(self, employee: User):
        """
        إعادة إسناد قسرية إلى موظف آخر (admin-only).
        لا تغيّر الحالة الجارية (OFFER_SELECTED/IN_PROGRESS/…)، فقط تبدّل الموظف.
        """
        if not employee or getattr(employee, "role", None) != "employee":
            raise ValidationError("لا يمكن الإسناد إلا لمستخدم بدور 'employee'.")
        self.assigned_employee = employee
        self.save(update_fields=["assigned_employee", "updated_at"])

    # -------------------------
    # دوال نزاع/إزالة نزاع (اختيارية — حسب منطقك في disputes.signals)
    # -------------------------
    @transaction.atomic
    def open_dispute(self):
        """
        وضع حالة النزاع. إبقاء has_dispute للتوافق مع الواجهات القديمة.
        (في المشاريع الكبيرة، يُفضّل إدارة هذا من خلال إشارات disputes.)
        """
        self.status = self.Status.DISPUTED
        self.has_dispute = True
        self.save(update_fields=["status", "has_dispute", "updated_at"])

    @transaction.atomic
    def close_dispute(self, resume_status: Optional[str] = None):
        """
        إغلاق النزاع وإزالة العلم. يمكن استئناف الحالة السابقة/المناسبة.
        إن لم يحدَّد resume_status: إن كانت الاتفاقية مقبولة فالأقرب IN_PROGRESS، وإلا AGREEMENT_PENDING.
        """
        self.has_dispute = False
        if resume_status:
            self.status = resume_status
        else:
            # قرار افتراضي بسيط: إن سبق اختيار عرض/اتفاقية → نعيدها إلى AGREEMENT_PENDING
            self.status = self.Status.AGREEMENT_PENDING if self.offer_selected_at else self.Status.NEW
        self.save(update_fields=["status", "has_dispute", "updated_at"])

    # -------------------------
    # روابط وتمثيل
    # -------------------------
    def get_absolute_url(self) -> str:
        try:
            return reverse("marketplace:request_detail", args=[self.pk])
        except Exception:
            return f"/marketplace/r/{self.pk}/"

    def __str__(self) -> str:
        return f"[{self.pk}] {self.title} — {self.get_status_display()}"

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["client"]),
            models.Index(fields=["assigned_employee"]),
            models.Index(fields=["agreement_due_at"]),
        ]
        # قيود سلامة إضافية على مستوى قاعدة البيانات
        constraints = [
            models.CheckConstraint(
                check=Q(estimated_duration_days__gt=0),
                name="request_duration_days_gt_0",
            ),
            models.CheckConstraint(
                check=Q(estimated_price__gte=0),
                name="request_estimated_price_gte_0",
            ),
        ]
        verbose_name = "طلب"
        verbose_name_plural = "طلبات"


class Offer(models.Model):
    # حالات العرض
    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        SELECTED = "selected", "العرض المختار"
        REJECTED = "rejected", "مرفوض"
        WITHDRAWN = "withdrawn", "مسحوب"

    STATUS_CHOICES = Status.choices  # توافق مع أي كود قديم يستخدم المتغيّر

    request = models.ForeignKey("marketplace.Request", related_name="offers", on_delete=models.CASCADE)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="offers", on_delete=models.CASCADE)

    proposed_duration_days = models.PositiveIntegerField()
    proposed_price = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        # ضمان وجود عرض مختار واحد فقط لكل طلب (شرطي)
        constraints = [
            models.UniqueConstraint(
                fields=["request"],
                condition=Q(status="selected"),
                name="uq_request_single_selected_offer",
            )
        ]

    # صلاحيات
    def can_view(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False) or getattr(user, "role", "") in ("admin", "manager", "finance"):
            return True
        return user.id in (self.request.client_id, self.employee_id)

    def can_select(self, user):
        return (
            getattr(user, "is_authenticated", False)
            and user.id == self.request.client_id
            and self.status == self.Status.PENDING
            and self.request.status == Request.Status.NEW
        )

    def can_reject(self, user):
        return (
            getattr(user, "is_authenticated", False)
            and user.id == self.request.client_id
            and self.status == self.Status.PENDING
        )

    def clean(self):
        if self.proposed_duration_days == 0:
            raise ValidationError("المدة المقترحة يجب أن تكون أكبر من صفر.")
        if self.proposed_price < 0:
            raise ValidationError("السعر المقترح لا يمكن أن يكون سالبًا.")

    def __str__(self):
        return f"Offer#{self.pk} R{self.request_id} by {self.employee}"


class Note(models.Model):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField("نص الملاحظة")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    is_internal = models.BooleanField("رؤية مقيدة (داخلي)", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ملاحظة"
        verbose_name_plural = "ملاحظات"

    def __str__(self):
        return f"Note#{self.pk} R{self.request_id} by {self.author_id}"
