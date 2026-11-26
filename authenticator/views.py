import os
import secrets
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.mail import send_mail
from django.contrib.auth.models import User
from dotenv import load_dotenv
from .models import Profile
import hashlib
import random
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from twilio.rest import Client  # Twilio for SMS
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.contrib.sessions.models import Session
load_dotenv()
import logging
logger = logging.getLogger(__name__)
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import Profile

from django.urls import reverse

def send_verification_email(user, request):
    token = secrets.token_urlsafe(32)
    user.profile.verification_token = token
    user.profile.save(update_fields=["verification_token"])
    verification_url = request.build_absolute_uri(
        reverse("verify_email", kwargs={"token": token})
    )
    send_mail(
        "Email Verification",
        f"Click the link to verify your email: {verification_url}",
        os.getenv("EMAIL_HOST_USER"),
        [user.email],
        fail_silently=False,
    )

def register(request):
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")
        mobile_number = request.POST.get("mobile_number", "").strip()
        account_type = request.POST.get("account_type", "CUSTOMER").upper()
        terms_accepted = request.POST.get("terms_accepted")
        # Employee information
        employee_id = request.POST.get("employee_id", "").strip()
        department = request.POST.get("department", "").strip()
        designation = request.POST.get("designation", "").strip()

        # Basic validation
        if not terms_accepted:
            messages.error(request, "Please accept the terms and conditions.")
            return redirect("register")

        if not all([first_name, last_name, username, email, password, mobile_number]):
            messages.error(request, "Please fill in all required fields.")
            return redirect("register")

        if account_type not in ["CUSTOMER", "EMPLOYEE"]:
            messages.error(request, "Invalid account type.")
            return redirect("register")

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already taken.")
            return redirect("register")

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email already registered.")
            return redirect("register")

        if password != confirm_password:
            messages.error(request, "Password and confirm password do not match.")
            return redirect("register")

        # Employee-specific validation
        if account_type == "EMPLOYEE":
            if not employee_id or not department or not designation:
                messages.error(
                    request,
                    "Employee ID, department and designation are required."
                )
                return redirect("register")

            if Profile.objects.filter(employee_id__iexact=employee_id).exists():
                messages.error(request, "This Employee ID is already registered.")
                return redirect("register")

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )

                # Profile is automatically created by the post_save signal.
                profile = Profile.objects.get(user=user)

                profile.mobile_number = mobile_number
                profile.account_type = account_type

                if account_type == "EMPLOYEE":
                    profile.role = "staff"
                    profile.employee_id = employee_id
                    profile.department = department
                    profile.designation = designation
                    profile.approval_status = "PENDING"

                    # Assigned by Admin during approval
                    profile.level = None
                    profile.reporting_manager = None

                else:
                    profile.role = "customer"
                    profile.approval_status = "NOT_REQUIRED"
                profile.save()
                profile.generate_otp()
                send_verification_email(user, request)

            if account_type == "EMPLOYEE":
                messages.success(
                    request,
                    "Registration submitted successfully. "
                    "Please verify your email. Your account will be activated "
                    "after Admin approval."
                )
            else:
                messages.success(
                    request,
                    "Registration successful! Please verify your email to log in."
                )

            return redirect("login")

        except Exception:
            logger.exception("Registration failed.")
            messages.error(
                request,
                "Unable to complete registration. Please try again."
            )
            return redirect("register")

    return render(request, "signup.html")


def login_view(request):
    if request.method == "POST":
        user_input = request.POST.get("username_or_email", "").strip()
        password = request.POST.get("password", "")
        remember = request.POST.get("remember")

        if not user_input or not password:
            messages.error(request, "Please enter your username/email and password.")
            return render(request, "login.html")

        # Resolve email to username
        if "@" in user_input:
            user_record = User.objects.filter(
                email__iexact=user_input
            ).first()

            if not user_record:
                messages.error(request, "Invalid username/email or password.")
                return render(request, "login.html")

            username = user_record.username
        else:
            username = user_input

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is None:
            messages.error(request, "Invalid username/email or password.")
            return render(request, "login.html")

        profile = user.profile

        # Email verification check
        if not profile.is_email_verified:
            messages.error(request, "Please verify your email before logging in.")
            return render(request, "login.html")

        # Employee approval check
        if profile.account_type == "EMPLOYEE":

            if profile.approval_status == "PENDING":
                messages.warning(
                    request,
                    "Your employee registration is awaiting Admin approval."
                )
                return render(request, "login.html")

            if profile.approval_status == "REJECTED":
                messages.error(
                    request,
                    "Your employee registration has been rejected. "
                    "Please contact the administrator."
                )
                return render(request, "login.html")

            if profile.approval_status != "APPROVED":
                messages.error(
                    request,
                    "Your employee account is not approved."
                )
                return render(request, "login.html")

        # Customer accounts do not require employee approval
        login(request, user)

        if remember:
            request.session.set_expiry(21600)
        else:
            request.session.set_expiry(0)

        messages.success(request, "Login successful!")
        return redirect("home")

    return render(request, "login.html")


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully!")
    return redirect('login')

def verify_email(request, token):
    try:
        profile = Profile.objects.get(verification_token=token)
        profile.is_email_verified = True
        profile.verification_token = ''
        profile.save()
        messages.success(request, "Email verified successfully! You can now log in.")
        return redirect('login')
    except Profile.DoesNotExist:
        messages.error(request, "Invalid verification link.")
        return redirect('register')

def send_sms_otp(mobile_number, otp):
    client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
    message = client.messages.create(
        body=f'Your password reset OTP is: {otp}',
        from_=os.getenv('TWILIO_PHONE_NUMBER'),
        to=mobile_number
    )
    return message.sid

def forgot_password(request):
    if request.method == 'POST':
        identifier = request.POST['identifier'] 
        try:
            user = User.objects.get(email=identifier) if '@' in identifier else User.objects.get(profile__mobile_number=identifier)
            otp = user.profile.generate_otp()

            if '@' in identifier:  
                send_mail(
                    'Password Reset OTP',
                    f'Your OTP for password reset is: {otp}',
                    os.getenv('EMAIL_HOST_USER'),
                    [user.email],
                    fail_silently=False,
                )
                messages.info(request, "An OTP has been sent to your email.")
            else:  
                send_sms_otp(user.profile.mobile_number, otp)
                messages.info(request, "An OTP has been sent to your mobile number.")

            return redirect('verify_otp', user_name=user.username)  
        except User.DoesNotExist:
            messages.error(request, "No account found with this identifier.")
            return redirect('forgot_password')

    return render(request, 'forgot_password.html')

def verify_otp(request, user_name):
    user = User.objects.get(username=user_name)
    if request.method == 'POST':
        otp = request.POST['otp']
        if user.profile.otp == otp:
            messages.success(request, "OTP verified successfully. Please set a new password.")
            # return redirect('reset_password', otp_token=user.profile.generate_otp_token()) 
            return render(request, 'reset_password.html', {'otp_token': user.profile.generate_otp_token()})
        else:
            messages.error(request, "Invalid OTP.")
    return render(request, 'verify_otp.html', {'user': user})

@login_required
def logout_from_all_devices(request):
    user = request.user
    
    # Clear all active sessions for the user
    # Assuming sessions are stored in Django's session framework and each device has a unique session
    for session in user.session_set.all():
        session.delete()  # Delete the session for the current device
    # Optionally, log the user out from the current session as well
    logout(request)
    
    messages.success(request, "You have been logged out from all devices.")
    return redirect('login')

def reset_password(request, otp_token):
    # Fetch the user using the otp_token
    try:
        user_profile = Profile.objects.get(otp_token=otp_token)
        user = user_profile.user
    except Profile.DoesNotExist:
        messages.error(request, "Invalid or expired OTP token.")
        return redirect('login')

    if request.method == 'POST':
        new_password = request.POST['new_password']
        confirm_password = request.POST['confirm_password']
        logout_devices = request.POST['logout_devices']
        if logout_devices and logout_devices == "on":
            logout_from_all_devices(request)
        # Check if passwords match
        if new_password == confirm_password:
            user.set_password(new_password)
            user.save()
            messages.success(request, "Password reset successfully.")
            return redirect('login')
        else:
            messages.error(request, "Passwords do not match.")
    
    return render(request, 'reset_password.html', {'user': user})

@login_required
def delete_account(request):
    user = request.user
    if request.method == 'POST':
        user.delete()
        messages.success(request, "Your account has been deleted successfully.")
        return redirect('register')
    return render(request, 'delete_account.html')


def verify_mobile(request, user_id):
    user = User.objects.get(id=user_id)
    profile = user.profile

    if request.method == 'POST':
        otp = request.POST['otp']
        # Check if OTP matches and is still valid
        if profile.mobile_otp == otp and profile.mobile_otp_expiration > timezone.now():
            profile.is_mobile_number_verified = True  # Mark mobile as verified
            profile.mobile_otp = ''  # Clear OTP after successful verification
            profile.mobile_otp_expiration = None  # Clear expiration time
            profile.save()

            messages.success(request, "Mobile number verified successfully!")
            return redirect('home')  # Redirect to home page or another relevant page
        else:
            messages.error(request, "Invalid or expired OTP.")

    return render(request, 'verify_mobile.html', {'user': user})



from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Profile


def is_system_admin(user):
    if not user.is_authenticated:
        return False

    return (
        user.is_superuser
        or (
            hasattr(user, "profile")
            and user.profile.role == "admin"
        )
    )

@login_required
def pending_employee_approvals(request):
    if not is_system_admin(request.user):
        messages.error(request, "You are not authorized to access this page.")
        return redirect("home")

    pending_employees = Profile.objects.filter(
        account_type="EMPLOYEE",
        approval_status="PENDING"
    ).select_related("user").order_by("-created_at")

    approved_managers = Profile.objects.filter(
        account_type="EMPLOYEE",
        approval_status="APPROVED",
        level__in=[2, 3, 4]
    ).select_related("user").order_by("user__first_name")

    return render(
        request,
        "admin/pending_employee_approvals.html",
        {
            "pending_employees": pending_employees,
            "approved_managers": approved_managers,
        }
    )

@login_required
@require_POST
def review_employee_registration(request, profile_id):
    if not is_system_admin(request.user):
        messages.error(request, "You are not authorized to perform this action.")
        return redirect("home")

    try:
        with transaction.atomic():
            profile = get_object_or_404(
                Profile.objects.select_for_update().select_related("user"),
                pk=profile_id,
                account_type="EMPLOYEE",
                approval_status="PENDING"
            )

            action = request.POST.get("action")

            if action == "reject":
                rejection_reason = request.POST.get(
                    "rejection_reason", ""
                ).strip()

                if not rejection_reason:
                    messages.error(
                        request,
                        "Please provide a rejection reason."
                    )
                    return redirect("pending_employee_approvals")

                profile.approval_status = "REJECTED"
                profile.rejection_reason = rejection_reason
                profile.approved_by = request.user
                profile.approved_at = timezone.now()

                profile.save()

                messages.success(
                    request,
                    f"Registration rejected for {profile.user.get_full_name()}."
                )

            elif action == "approve":
                level = request.POST.get("level")
                department = request.POST.get("department", "").strip()
                designation = request.POST.get("designation", "").strip()
                reporting_manager_id = request.POST.get(
                    "reporting_manager"
                )

                if not level or not department or not designation:
                    messages.error(
                        request,
                        "Level, department and designation are required."
                    )
                    return redirect("pending_employee_approvals")

                level = int(level)

                if level not in [1, 2, 3, 4, 5]:
                    raise ValidationError("Invalid organizational level.")

                reporting_manager = None

                if reporting_manager_id:
                    reporting_manager = Profile.objects.filter(
                        pk=reporting_manager_id,
                        account_type="EMPLOYEE",
                        approval_status="APPROVED",
                        level=level + 1
                    ).first()

                    if not reporting_manager:
                        raise ValidationError("Invalid reporting manager selected.")

                # Levels 1–3 must have their immediate manager.
                if level in [1, 2, 3] and not reporting_manager:
                    raise ValidationError(
                        "A reporting manager is required for this level."
                    )

                # MD and Admin have no reporting manager.
                if level in [4, 5] and reporting_manager:
                    raise ValidationError(
                        "MD and Admin cannot have a reporting manager."
                    )

                profile.level = level
                profile.department = department
                profile.designation = designation
                profile.reporting_manager = reporting_manager

                # Map organizational level to existing system role.
                profile.role = (
                    "admin" if level == 5
                    else "staff" if level == 1
                    else "manager"
                )

                profile.approval_status = "APPROVED"
                profile.approved_by = request.user
                profile.approved_at = timezone.now()
                profile.rejection_reason = ""

                profile.full_clean()
                profile.save()

                messages.success(
                    request,
                    f"{profile.user.get_full_name()} has been approved."
                )

            else:
                messages.error(request, "Invalid approval action.")

    except (ValidationError, ValueError) as exc:
        error = exc.messages if isinstance(exc, ValidationError) else str(exc)
        messages.error(request, error)

    return redirect("pending_employee_approvals")

@login_required
def my_profile(request):
    user = request.user
    profile = user.profile

    return render(
        request,
        "accounts/my_profile.html",
        {
            "profile_user": user,
            "profile": profile,
        }
    )


from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Profile


def employee_api_response(message, code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {"success": False, "error": message},
        status=code
    )


@api_view(["GET", "POST"])
def employee_management_api(request):

    # Admin-only access
    if not request.user.is_authenticated:
        return employee_api_response(
            "Authentication required.",
            status.HTTP_401_UNAUTHORIZED
        )

    if not is_system_admin(request.user):
        return employee_api_response(
            "You are not authorized to manage employees.",
            status.HTTP_403_FORBIDDEN
        )

    # -------------------------------------------------
    # GET: Employee listing / employee details
    # -------------------------------------------------
    if request.method == "GET":

        employee_id = request.query_params.get("id")

        if employee_id:
            profile = Profile.objects.filter(
                pk=employee_id,
                account_type="EMPLOYEE"
            ).select_related(
                "user", "reporting_manager__user"
            ).first()

            if not profile:
                return employee_api_response(
                    "Employee not found.",
                    status.HTTP_404_NOT_FOUND
                )

            user = profile.user

            return Response({
                "success": True,
                "data": {
                    "id": profile.id,
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "mobile_number": profile.mobile_number,
                    "employee_id": profile.employee_id,
                    "department": profile.department,
                    "designation": profile.designation,
                    "level": profile.level,
                    "role": profile.role,
                    "reporting_manager_id": profile.reporting_manager_id,
                    "reporting_manager": (
                        profile.reporting_manager.user.get_full_name()
                        or profile.reporting_manager.user.username
                        if profile.reporting_manager else None
                    ),
                    "is_active": user.is_active,
                    "approval_status": profile.approval_status,
                    "is_email_verified": profile.is_email_verified,
                    "created_at": profile.created_at.isoformat(),
                }
            })

        # DataTables pagination
        try:
            start = max(0, int(request.query_params.get("start", 0)))
            length = max(
                1,
                min(int(request.query_params.get("length", 10)), 100)
            )
        except (TypeError, ValueError):
            return employee_api_response("Invalid pagination parameters.")

        search = request.query_params.get(
            "search[value]", ""
        ).strip()

        queryset = Profile.objects.filter(
            account_type="EMPLOYEE"
        ).select_related(
            "user", "reporting_manager__user"
        )

        records_total = queryset.count()

        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__email__icontains=search)
                | Q(employee_id__icontains=search)
                | Q(department__icontains=search)
                | Q(designation__icontains=search)
            )

        # Optional filters
        department = request.query_params.get("department")
        level = request.query_params.get("level")
        account_status = request.query_params.get("account_status")

        if department:
            queryset = queryset.filter(department=department)

        if level:
            queryset = queryset.filter(level=level)

        if account_status == "active":
            queryset = queryset.filter(user__is_active=True)
        elif account_status == "inactive":
            queryset = queryset.filter(user__is_active=False)

        records_filtered = queryset.count()

        employees = queryset.order_by(
            "user__first_name",
            "user__last_name"
        )[start:start + length]

        data = []

        for profile in employees:
            user = profile.user

            data.append({
                "id": profile.id,
                "user_id": user.id,
                "name": user.get_full_name() or user.username,
                "username": user.username,
                "email": user.email,
                "mobile_number": profile.mobile_number,
                "employee_id": profile.employee_id,
                "department": profile.department,
                "designation": profile.designation,
                "level": profile.level,
                "level_display": profile.get_level_display(),
                "role": profile.role,
                "reporting_manager": (
                    profile.reporting_manager.user.get_full_name()
                    or profile.reporting_manager.user.username
                    if profile.reporting_manager else None
                ),
                "reporting_manager_id": profile.reporting_manager_id,
                "is_active": user.is_active,
                "approval_status": profile.approval_status,
            })

        # Reporting manager options for the frontend
        managers = Profile.objects.filter(
            account_type="EMPLOYEE",
            approval_status="APPROVED",
            level__in=[2, 3, 4],
            user__is_active=True
        ).select_related("user").order_by(
            "user__first_name",
            "user__last_name"
        )

        manager_data = [
            {
                "id": manager.id,
                "name": (
                    manager.user.get_full_name()
                    or manager.user.username
                ),
                "employee_id": manager.employee_id,
                "level": manager.level,
                "department": manager.department,
            }
            for manager in managers
        ]

        departments = list(
            Profile.objects.filter(
                account_type="EMPLOYEE"
            ).exclude(
                department__isnull=True
            ).exclude(
                department=""
            ).values_list(
                "department", flat=True
            ).distinct().order_by("department")
        )

        return Response({
            "success": True,
            "draw": int(request.query_params.get("draw", 1)),
            "recordsTotal": records_total,
            "recordsFiltered": records_filtered,
            "data": data,
            "managers": manager_data,
            "departments": departments,
        })

    # -------------------------------------------------
    # POST: Employee management actions
    # -------------------------------------------------

    action = request.data.get("action", "").strip().lower()

    try:
        with transaction.atomic():

            # =============================================
            # CREATE EMPLOYEE
            # =============================================
            if action == "create":

                username = request.data.get("username", "").strip()
                email = request.data.get("email", "").strip().lower()
                password = request.data.get("password", "")

                first_name = request.data.get("first_name", "").strip()
                last_name = request.data.get("last_name", "").strip()

                if not all([
                    username, email, password,
                    first_name, last_name
                ]):
                    return employee_api_response(
                        "Username, email, password, first name and last name are required."
                    )

                if User.objects.filter(username__iexact=username).exists():
                    return employee_api_response("Username already exists.")

                if User.objects.filter(email__iexact=email).exists():
                    return employee_api_response("Email already exists.")

                employee_id = request.data.get("employee_id", "").strip()

                if not employee_id:
                    return employee_api_response("Employee ID is required.")

                if Profile.objects.filter(
                    employee_id__iexact=employee_id
                ).exists():
                    return employee_api_response(
                        "Employee ID already exists."
                    )

                level = int(request.data.get("level"))

                if level not in [1, 2, 3, 4, 5]:
                    return employee_api_response("Invalid employee level.")

                manager_id = request.data.get("reporting_manager_id")

                manager = None

                if manager_id:
                    manager = Profile.objects.filter(
                        pk=manager_id,
                        account_type="EMPLOYEE",
                        approval_status="APPROVED",
                        user__is_active=True,
                        level=level + 1
                    ).first()

                    if not manager:
                        return employee_api_response(
                            "Invalid reporting manager selected."
                        )

                if level in [1, 2, 3] and not manager:
                    return employee_api_response(
                        "A reporting manager is required for this level."
                    )

                if level in [4, 5] and manager:
                    return employee_api_response(
                        "Level 4 and Level 5 employees cannot have a reporting manager."
                    )

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True
                )

                profile = user.profile

                profile.account_type = "EMPLOYEE"
                profile.approval_status = "APPROVED"
                profile.approved_by = request.user
                profile.approved_at = timezone.now()

                profile.is_email_verified = True
                profile.mobile_number = request.data.get(
                    "mobile_number", ""
                ).strip()

                profile.employee_id = employee_id
                profile.department = request.data.get(
                    "department", ""
                ).strip()
                profile.designation = request.data.get(
                    "designation", ""
                ).strip()

                profile.level = level
                profile.reporting_manager = manager

                profile.role = (
                    "admin" if level == 5
                    else "staff" if level == 1
                    else "manager"
                )

                profile.full_clean()
                profile.save()

                return Response({
                    "success": True,
                    "message": "Employee created and approved successfully.",
                    "employee_id": profile.id,
                    "user_id": user.id,
                }, status=status.HTTP_201_CREATED)

            # =============================================
            # FETCH EMPLOYEE FOR UPDATE / OTHER ACTIONS
            # =============================================
            profile_id = request.data.get("employee_id")

            profile = Profile.objects.select_for_update().filter(
                pk=profile_id,
                account_type="EMPLOYEE"
            ).select_related("user").first()

            if not profile:
                return employee_api_response(
                    "Employee not found.",
                    status.HTTP_404_NOT_FOUND
                )

            user = profile.user

            # =============================================
            # UPDATE EMPLOYEE
            # =============================================
            if action == "update":

                first_name = request.data.get(
                    "first_name", user.first_name
                ).strip()

                last_name = request.data.get(
                    "last_name", user.last_name
                ).strip()

                email = request.data.get(
                    "email", user.email
                ).strip().lower()

                username = request.data.get(
                    "username", user.username
                ).strip()

                if not all([first_name, last_name, email, username]):
                    return employee_api_response(
                        "Name, username and email are required."
                    )

                if User.objects.filter(
                    username__iexact=username
                ).exclude(pk=user.pk).exists():
                    return employee_api_response("Username already exists.")

                if User.objects.filter(
                    email__iexact=email
                ).exclude(pk=user.pk).exists():
                    return employee_api_response("Email already exists.")

                new_employee_id = request.data.get(
                    "new_employee_id", profile.employee_id
                ).strip()

                if not new_employee_id:
                    return employee_api_response("Employee ID is required.")

                if Profile.objects.filter(
                    employee_id__iexact=new_employee_id
                ).exclude(pk=profile.pk).exists():
                    return employee_api_response(
                        "Employee ID already exists."
                    )

                new_level = int(request.data.get("level", profile.level))

                if new_level not in [1, 2, 3, 4, 5]:
                    return employee_api_response("Invalid employee level.")

                # Do not change a manager's level while they have subordinates.
                if (
                    profile.team_members.exists()
                    and new_level != profile.level
                ):
                    return employee_api_response(
                        "Reassign this employee's subordinates before changing their level."
                    )

                manager_id = request.data.get(
                    "reporting_manager_id",
                    profile.reporting_manager_id
                )

                manager = None

                if manager_id:
                    manager = Profile.objects.filter(
                        pk=manager_id,
                        account_type="EMPLOYEE",
                        approval_status="APPROVED",
                        user__is_active=True,
                        level=new_level + 1
                    ).exclude(pk=profile.pk).first()

                    if not manager:
                        return employee_api_response(
                            "Invalid reporting manager selected."
                        )

                if new_level in [1, 2, 3] and not manager:
                    return employee_api_response(
                        "A reporting manager is required for this level."
                    )

                if new_level in [4, 5] and manager:
                    return employee_api_response(
                        "Level 4 and Level 5 employees cannot have a reporting manager."
                    )

                user.first_name = first_name
                user.last_name = last_name
                user.email = email
                user.username = username
                user.save()

                profile.mobile_number = request.data.get(
                    "mobile_number", profile.mobile_number
                ).strip()

                profile.employee_id = new_employee_id

                profile.department = request.data.get(
                    "department", profile.department
                ).strip()

                profile.designation = request.data.get(
                    "designation", profile.designation
                ).strip()

                profile.level = new_level
                profile.reporting_manager = manager

                profile.role = (
                    "admin" if new_level == 5
                    else "staff" if new_level == 1
                    else "manager"
                )

                profile.full_clean()
                profile.save()

                return Response({
                    "success": True,
                    "message": "Employee updated successfully."
                })

            # =============================================
            # ACTIVATE / DEACTIVATE
            # =============================================
            elif action == "toggle_status":

                if user.pk == request.user.pk:
                    return employee_api_response(
                        "You cannot deactivate your own account."
                    )

                new_status = request.data.get("is_active")

                if not isinstance(new_status, bool):
                    return employee_api_response(
                        "is_active must be true or false."
                    )

                if not new_status and profile.team_members.exists():
                    return employee_api_response(
                        "Reassign this employee's subordinates before deactivating their account."
                    )

                user.is_active = new_status
                user.save(update_fields=["is_active"])

                return Response({
                    "success": True,
                    "message": (
                        "Employee account activated successfully."
                        if new_status
                        else "Employee account deactivated successfully."
                    ),
                    "is_active": user.is_active,
                })

            # =============================================
            # ADMIN PASSWORD RESET
            # =============================================
            elif action == "reset_password":

                new_password = request.data.get("password", "")

                if len(new_password) < 8:
                    return employee_api_response(
                        "Password must contain at least 8 characters."
                    )

                user.set_password(new_password)
                user.save(update_fields=["password"])

                return Response({
                    "success": True,
                    "message": "Employee password reset successfully."
                })

            # =============================================
            # SAFE DELETE: DEACTIVATION
            # =============================================
            elif action == "delete":

                if user.pk == request.user.pk:
                    return employee_api_response(
                        "You cannot delete your own account."
                    )

                if profile.team_members.exists():
                    return employee_api_response(
                        "Reassign this employee's subordinates before removing the account."
                    )

                # Preserve tender/task history and employee attribution.
                user.is_active = False
                user.save(update_fields=["is_active"])

                return Response({
                    "success": True,
                    "message": (
                        "Employee account deactivated. "
                        "Historical tender and task records have been preserved."
                    ),
                    "is_active": False,
                })

            return employee_api_response("Invalid employee management action.")

    except (ValidationError, ValueError, TypeError) as exc:
        errors = (
            exc.messages
            if isinstance(exc, ValidationError)
            else str(exc)
        )

        return employee_api_response(errors)

    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Employee management API failed."
        )

        return employee_api_response(
            "Unable to process employee management request.",
            status.HTTP_500_INTERNAL_SERVER_ERROR
        )
