from functools import wraps
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

def admin_required(view_func):
    """
    Custom decorator to check if the user is an admin (superuser).
    """
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, "You do not have permission to access this page.")
        return redirect('home')  # Replace 'home' with the name of your fallback route
    return _wrapped_view

def role_required(allowed_roles):
    """
    Decorator to check if the user's role matches one of the allowed roles.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated:
                # Access role from Profile model
                user_role = request.user.profile.role
                if request.user.is_superuser or user_role in allowed_roles:
                    return view_func(request, *args, **kwargs)
            messages.error(request, "You do not have permission to access this page.")
            return redirect("home")  # Replace 'home' with your desired URL name
        return _wrapped_view
    return decorator
