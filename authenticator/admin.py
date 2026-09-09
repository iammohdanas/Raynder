from django.contrib import admin
from .models import Profile

class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'mobile_number', 'is_email_verified']
    list_filter = ['role', 'is_email_verified']
    search_fields = ['user__username', 'mobile_number']

admin.site.register(Profile, ProfileAdmin)