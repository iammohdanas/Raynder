from django.contrib import admin
from .models import Tender, TenderPriority

# Register your models here.
admin.site.register(Tender)
admin.site.register(TenderPriority)