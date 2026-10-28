from django.contrib import admin
from .models import ChatConversation, ChatMessage, EvaluationTestCase , EvaluationResult, EvaluationRun
# Register your models here.
admin.site.register(ChatConversation)
admin.site.register(ChatMessage)
admin.site.register(EvaluationTestCase)
admin.site.register(EvaluationResult)
admin.site.register(EvaluationRun)