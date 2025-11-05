# core/permissions.py
from django.core.exceptions import PermissionDenied

def require_role(*roles):
    def _decorator(view):
        def _wrapped(request, *args, **kwargs):
            u = request.user
            if not u.is_authenticated:
                raise PermissionDenied("يلزم تسجيل الدخول")
            role = getattr(u, "role", None)
            if getattr(u, "is_staff", False) or role in roles:
                return view(request, *args, **kwargs)
            raise PermissionDenied("ليست لديك صلاحية")
        return _wrapped
    return _decorator
