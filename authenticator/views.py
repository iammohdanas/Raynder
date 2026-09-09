import os
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

def send_verification_email(user):
    token = hashlib.sha256(str(random.random()).encode('utf-8')).hexdigest()
    user.profile.verification_token = token
    user.profile.save()
    verification_url = f'http://localhost:8000/verify-email/{token}/'
    send_mail(
        'Email Verification',
        f'Click the link to verify your email: {verification_url}',
        os.getenv('EMAIL_HOST_USER'),  # Update with your email as required 
        [user.email],
        fail_silently=False,
    )

def register(request):
    if request.method == 'POST':
        first_name = request.POST['first_name']
        last_name = request.POST['last_name']
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']
        mobile_number = request.POST['mobile_number']
        terms_accepted = request.POST.get('terms_accepted')

        if not terms_accepted:
            messages.error(request, "Please accept the terms and conditions.")
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return redirect('register')
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect('register')
        if password != confirm_password:
            messages.error(request, "Password and Confirm password didn't matched.")
            return redirect('register')

        user = User.objects.create_user(
            username=username, email=email, password=password, first_name=first_name, last_name=last_name
        )
        profile = Profile.objects.get(user=user)
        profile.mobile_number = mobile_number
        profile.save()

        # Generate and send OTP to mobile number
        otp = profile.generate_otp()
        profile.mobile_otp = otp
        profile.mobile_otp_expiration = timezone.now() + timedelta(minutes=10)  # OTP expiration time (e.g., 10 minutes)
        profile.save()

        # send_sms_otp(mobile_number, otp)
        
        send_verification_email(user)  # For email verification
        messages.info(request, "Registration successful! Please verify your email and mobile number.")
        # return redirect('verify_mobile', user_id=user.id)  # Redirect to mobile verification page
        return redirect('login')

    return render(request, 'signup.html')

def login_view(request):
    if request.method == 'POST':
        user_input = request.POST.get('username_or_email').strip()
        password = request.POST.get('password')
        remember = request.POST.get('remember')
        # Initialize username variable
        username = None
        
        if '@' in user_input:
            user = User.objects.filter(email=user_input).first()
            if user:
                username = user.username
        else:
            username = user_input  # If not an email, treat it as a username
        
        if username:  # Ensure username is set before calling authenticate
            user = authenticate(request, username=username, password=password)
            if user:
                if user.profile.is_email_verified:
                    login(request, user)
                    # Set session expiry based on "Remember Me"
                    if remember:
                        request.session.set_expiry(21600)  # 6 hrs
                    else:
                        request.session.set_expiry(0)  # Browser close = session expiry
                    messages.success(request, "Login successful!")
                    return redirect('home')
                else:
                    messages.error(request, "Please verify your email first.")
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "User doesn't exisit")

    return render(request, 'login.html')

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
            profile.is_mobile_verified = True  # Mark mobile as verified
            profile.mobile_otp = ''  # Clear OTP after successful verification
            profile.mobile_otp_expiration = None  # Clear expiration time
            profile.save()

            messages.success(request, "Mobile number verified successfully!")
            return redirect('home')  # Redirect to home page or another relevant page
        else:
            messages.error(request, "Invalid or expired OTP.")

    return render(request, 'verify_mobile.html', {'user': user})

