
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages


def get_user_profile(user):
    """Safely retrieve the user's Profile."""
    try:
        return user.profile
    except AttributeError:
        return None


def is_system_admin(user):
    """
    System-wide access:
    - Django superuser
    - Approved Level 5 Admin
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    profile = get_user_profile(user)

    return bool(
        profile
        and profile.account_type == "EMPLOYEE"
        and profile.approval_status == "APPROVED"
        and profile.level == 5
    )


def is_approved_employee(user):
    """Check whether the user is an approved employee."""
    profile = get_user_profile(user)

    return bool(
        user.is_authenticated
        and profile
        and profile.account_type == "EMPLOYEE"
        and profile.approval_status == "APPROVED"
    )


def has_role(user, allowed_roles):
    """Check whether the user's system role is permitted."""
    if is_system_admin(user):
        return True

    profile = get_user_profile(user)

    return bool(
        profile
        and profile.account_type == "EMPLOYEE"
        and profile.approval_status == "APPROVED"
        and profile.role in allowed_roles
    )


def has_level(user, allowed_levels):
    """Check whether the employee's organizational level is permitted."""
    if is_system_admin(user):
        return True

    profile = get_user_profile(user)

    return bool(
        profile
        and profile.account_type == "EMPLOYEE"
        and profile.approval_status == "APPROVED"
        and profile.level in allowed_levels
    )


# --------------------------------------------------
# ADMIN DECORATOR
# --------------------------------------------------

def admin_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):

        if is_system_admin(request.user):
            return view_func(request, *args, **kwargs)

        messages.error(
            request,
            "You do not have permission to access this page."
        )

        return redirect("home")

    return _wrapped_view


# --------------------------------------------------
# ROLE-BASED HTML DECORATOR
# --------------------------------------------------

def role_required(allowed_roles):

    def decorator(view_func):

        @login_required
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):

            if has_role(request.user, allowed_roles):
                return view_func(request, *args, **kwargs)

            messages.error(
                request,
                "You do not have permission to access this page."
            )

            return redirect("home")

        return _wrapped_view

    return decorator


# --------------------------------------------------
# ROLE-BASED API DECORATOR
# --------------------------------------------------

def role_required_api(allowed_roles):

    def decorator(view_func):

        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):

            if not request.user.is_authenticated:
                return JsonResponse({
                    "success": False,
                    "message": "Authentication required."
                }, status=401)

            if has_role(request.user, allowed_roles):
                return view_func(request, *args, **kwargs)

            return JsonResponse({
                "success": False,
                "message": "You do not have permission to perform this action."
            }, status=403)

        return _wrapped_view

    return decorator


# --------------------------------------------------
# LEVEL-BASED API DECORATOR
# --------------------------------------------------

def level_required_api(allowed_levels):

    def decorator(view_func):

        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):

            if not request.user.is_authenticated:
                return JsonResponse({
                    "success": False,
                    "message": "Authentication required."
                }, status=401)

            if has_level(request.user, allowed_levels):
                return view_func(request, *args, **kwargs)

            return JsonResponse({
                "success": False,
                "message": "Insufficient organizational permissions."
            }, status=403)

        return _wrapped_view

    return decorator
