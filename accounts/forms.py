# accounts/forms.py
from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import normalize_to_e164

User = get_user_model()


# ---------------------------------------------
# تسجيل الدخول بالبريد الإلكتروني فقط
# ---------------------------------------------
class LoginForm(forms.Form):
    """
    نموذج تسجيل الدخول عبر البريد الإلكتروني + كلمة المرور.
    يدعم تمرير request لاستخدام Backends التي تعتمد على الطلب.
    """
    email = forms.EmailField(
        label="البريد الإلكتروني",
        widget=forms.EmailInput(attrs={
            "placeholder": "example@mail.com",
            "autocomplete": "email",
            "class": "input",
            "dir": "ltr",
        }),
    )
    password = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "autocomplete": "current-password",
            "class": "input",
        }),
        strip=False,
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request  # لتمريره إلى authenticate إذا توفر

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        validate_email(email)
        return email

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")

        if email and password:
            # ملاحظة: يفترض وجود Backend يدعم المصادقة بالبريد.
            user = authenticate(self.request, email=email, password=password) if self.request \
                   else authenticate(email=email, password=password)

            if not user:
                raise ValidationError("بيانات الدخول غير صحيحة.")
            if not user.is_active:
                raise ValidationError("الحساب غير مفعّل.")
            cleaned["user"] = user
        return cleaned


# ---------------------------------------------
# إنشاء حساب — البريد إلزامي، الجوال اختياري
# ---------------------------------------------
class RegisterForm(forms.ModelForm):
    """
    نموذج تسجيل مستخدم جديد:
    - البريد إلزامي وفريد (case-insensitive).
    - الجوال اختياري ويُطبع بصيغة E.164 إن أُدخل.
    - التحقق من قوة كلمة المرور عبر مدقّقات Django.
    """
    password1 = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": "input",
            "autocomplete": "new-password",
        }),
        strip=False,
    )
    password2 = forms.CharField(
        label="تأكيد كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": "input",
            "autocomplete": "new-password",
        }),
        strip=False,
    )

    class Meta:
        model = User
        fields = ["email", "phone", "name"]
        labels = {
            "email": "البريد الإلكتروني",
            "phone": "الجوال (اختياري)",
            "name": "الاسم",
        }
        widgets = {
            "email": forms.EmailInput(attrs={
                "class": "input",
                "placeholder": "example@mail.com",
                "autocomplete": "email",
                "dir": "ltr",
            }),
            "phone": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "05… أو 00966… أو +966…",
                "autocomplete": "tel",
                "dir": "ltr",
            }),
            "name": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "اسمك الكامل",
            }),
        }

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        validate_email(email)
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("هذا البريد مستخدم مسبقًا.")
        return email

    def clean_phone(self) -> str | None:
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return None
        try:
            return normalize_to_e164(phone)
        except ValidationError as e:
            raise ValidationError(e.messages[0] if getattr(e, "messages", None) else "رقم جوال غير صالح.")

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("كلمتا المرور غير متطابقتين.")

        # تحقق قوة كلمة المرور عبر مدقّقات Django الرسمية
        if p1:
            # أنشئ instance غير محفوظ لتمريره للمدققات (قد تعتمد على خصائص المستخدم)
            user_temp = User(email=(cleaned.get("email") or "").strip().lower(),
                             phone=cleaned.get("phone"),
                             name=cleaned.get("name"))
            try:
                validate_password(p1, user=user_temp)
            except ValidationError as e:
                # عرض جميع الرسائل بشكل واضح للمستخدم
                raise ValidationError(e.messages)
        return cleaned

    def save(self, commit: bool = True):
        # لا نستخدم تعبيرًا نوعيًا على user هنا لتجنّب تحذيرات أدوات التحليل
        user = super().save(commit=False)
        user.email = (self.cleaned_data["email"] or "").strip().lower()
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


# ---------------------------------------------
# تعديل الملف الشخصي
# ---------------------------------------------
class ProfileUpdateForm(forms.ModelForm):
    """
    تعديل بيانات الحساب: البريد/الاسم/الجوال.
    يحافظ على فرادة البريد ويطبع الجوال بصيغة E.164 إن أُدخل.
    """
    class Meta:
        model = User
        fields = ["email", "name", "phone"]
        labels = {
            "email": "البريد الإلكتروني",
            "name": "الاسم",
            "phone": "الجوال",
        }
        widgets = {
            "email": forms.EmailInput(attrs={
                "class": "input",
                "autocomplete": "email",
                "dir": "ltr",
            }),
            "name": forms.TextInput(attrs={"class": "input"}),
            "phone": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "05… أو +966…",
                "autocomplete": "tel",
                "dir": "ltr",
            }),
        }

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        validate_email(email)
        qs = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("هذا البريد مستخدم من حساب آخر.")
        return email

    def clean_phone(self) -> str | None:
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return None
        try:
            return normalize_to_e164(phone)
        except ValidationError as e:
            raise ValidationError(e.messages[0] if getattr(e, "messages", None) else "رقم جوال غير صالح.")
