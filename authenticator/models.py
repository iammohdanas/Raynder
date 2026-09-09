# import secrets
# import random
# from django.db import models
# from django.contrib.auth.models import User
# from django.db.models.signals import post_save
# from django.dispatch import receiver

# class Profile(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE)
#     mobile_number = models.CharField(max_length=15, blank=True, null=True)
#     is_email_verified = models.BooleanField(default=False)
#     verification_token = models.CharField(max_length=64, blank=True, null=True)
#     first_login_done = models.BooleanField(default=False)
#     otp = models.CharField(max_length=6, blank=True, null=True)
#     is_mobile_number_verified = models.BooleanField(default=False)
#     otp_token = models.CharField(max_length=64, blank=True, null=True)  # New field to store OTP token

#     def __str__(self):
#         return self.user.username

#     def generate_otp(self):
#         """Generate a 6-digit OTP and save it in the Profile."""
#         otp = f"{random.randint(100000, 999999)}"
#         self.otp = otp
#         self.save()
#         return otp

#     def generate_otp_token(self):
#         """Generate a secure OTP token and save it in the Profile."""
#         otp_token = secrets.token_urlsafe(32)  # Generate a 32-byte URL-safe token
#         self.otp_token = otp_token
#         self.save()
#         return otp_token


# @receiver(post_save, sender=User)
# def create_or_update_user_profile(sender, instance, created, **kwargs):
#     """Create or update the Profile when a User is saved."""
#     if created:
#         Profile.objects.create(user=instance)
#     else:
#         if hasattr(instance, 'profile'):
#             instance.profile.save()


from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.db import models
import secrets
import random

class Profile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('manager', 'Manager'),
        ('customer', 'Customer'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    mobile_number = models.CharField(max_length=15, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True, null=True)
    first_login_done = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, blank=True, null=True)
    is_mobile_number_verified = models.BooleanField(default=False)
    otp_token = models.CharField(max_length=64, blank=True, null=True)  # Store OTP token
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer',  # Default role for new users
    )

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def generate_otp(self):
        """Generate a 6-digit OTP and save it in the Profile."""
        otp = f"{random.randint(100000, 999999)}"
        self.otp = otp
        self.save()
        return otp

    def generate_otp_token(self):
        """Generate a secure OTP token and save it in the Profile."""
        otp_token = secrets.token_urlsafe(32)  # Generate a 32-byte URL-safe token
        self.otp_token = otp_token
        self.save()
        return otp_token

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Create or update the Profile when a User is saved."""
    if created:
        Profile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
