
import secrets

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta


class Profile(models.Model):

    # Existing system roles
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("staff", "Staff"),
        ("manager", "Manager"),
        ("customer", "Customer"),
    ]

    # Organizational hierarchy
    LEVEL_CHOICES = [
        (1, "Level 1 - Employee"),
        (2, "Level 2 - Manager"),
        (3, "Level 3 - HOD"),
        (4, "Level 4 - MD"),
        (5, "Level 5 - Admin"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    # Contact and verification
    mobile_number = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )
    is_email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(
        max_length=64,
        blank=True,
        null=True
    )
    first_login_done = models.BooleanField(default=False)

    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_token = models.CharField(max_length=64, blank=True, null=True)

    is_mobile_number_verified = models.BooleanField(default=False)
    mobile_otp = models.CharField(max_length=6, blank=True, null=True)
    mobile_otp_expiration = models.DateTimeField(null=True, blank=True)

    # Existing system role
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="customer"
    )

    # Organization information
    employee_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True
    )

    department = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    designation = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    level = models.PositiveSmallIntegerField(
        choices=LEVEL_CHOICES,
        null=True,
        blank=True
    )

    reporting_manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_members"
    )
    ACCOUNT_TYPE_CHOICES = [
            ("CUSTOMER", "Customer"),
            ("EMPLOYEE", "Employee"),
    ]

    APPROVAL_STATUS_CHOICES = [
        ("NOT_REQUIRED", "Not Required"),
        ("PENDING", "Pending Approval"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default="CUSTOMER"
    )

    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default="NOT_REQUIRED"
    )

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_employee_profiles"
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def clean(self):
        super().clean()

        if self.account_type == "CUSTOMER":
            if self.level or self.reporting_manager_id:
                raise ValidationError(
                    "Customer accounts cannot have an organizational level or reporting manager."
                )
            return

        if self.account_type == "EMPLOYEE":
            if not self.employee_id:
                raise ValidationError({"employee_id": "Employee ID is required."})

            if self.approval_status == "APPROVED" and not self.level:
                raise ValidationError({"level": "Approved employees must have an organizational level."})

        if self.level and self.level not in [1, 2, 3, 4, 5]:
            raise ValidationError({"level": "Invalid organizational level."})

        if self.level in [1, 2, 3] and not self.reporting_manager_id:
            raise ValidationError({"reporting_manager": "A reporting manager is required."})

        if self.level in [4, 5] and self.reporting_manager_id:
            raise ValidationError({"reporting_manager": "MD and Admin cannot have a reporting manager."})

        if self.reporting_manager_id:
            manager = self.reporting_manager

            if manager.pk == self.pk:
                raise ValidationError({"reporting_manager": "An employee cannot report to themselves."})

            if manager.account_type != "EMPLOYEE" or manager.approval_status != "APPROVED":
                raise ValidationError({"reporting_manager": "Reporting manager must be an approved employee."})

            if manager.level != self.level + 1:
                raise ValidationError({
                    "reporting_manager": "Employee must report to the immediately higher organizational level."
                })
    def generate_otp(self):
        """Generate and save a secure six-digit OTP."""
        self.otp = f"{secrets.randbelow(900000) + 100000}"
        self.save(update_fields=["otp", "updated_at"])
        return self.otp

    def generate_otp_token(self):
        """Generate and save a secure password-reset token."""
        self.otp_token = secrets.token_urlsafe(32)
        self.save(update_fields=["otp_token", "updated_at"])
        return self.otp_token


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a Profile automatically for newly created users."""
    if created:
        Profile.objects.get_or_create(user=instance)
