from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('delete-account/', views.delete_account, name='delete_account'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-otp/<str:user_name>/', views.verify_otp, name='verify_otp'),
    path('reset-password/<str:otp_token>/', views.reset_password, name='reset_password'),
    path('logout-all-devices/', views.logout_from_all_devices, name='logout_all_devices'),
]
