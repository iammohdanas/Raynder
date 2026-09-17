from django.http import HttpRequest


def permissions(request: HttpRequest) -> dict:
    """Injects user role permissions globally into every template context."""
    user = getattr(request, "user", None)

    # If the user is anonymous, deny all permissions
    if not user or not user.is_authenticated:
        return {
            "can_edit": False,
            "can_delete": False,
            "can_create": False,
            "user_role": None,
            "can_upload": False,
        }

    # Superusers bypass all restrictions
    if user.is_superuser:
        return {
            "can_edit": True,
            "can_delete": True,
            "can_create": True,
            "can_upload": True,
            "user_role": "admin",
        }

    # Fetch the role safely from the linked Profile model
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)

    return {
        "can_edit": role in ["admin", "manager"],
        "can_delete": role == "admin",
        "can_create": role in ["admin", "manager"],
        "can_upload": role in ["admin", "manager"],
        "user_role": role,
    }