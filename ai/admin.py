from django.contrib import admin
from .models import ChatConversation, ChatMessage
# Register your models here.
admin.site.register(ChatConversation)
admin.site.register(ChatMessage)