from django.contrib import admin
from .models import Tender, TenderDocument, TenderPriority, DocumentChunk,MyTender , TenderDecision, ExecutionActivity, ExecutionWorkflowTemplate, TenderExecution

# Register your models here.
admin.site.register(Tender)
admin.site.register(TenderPriority)
admin.site.register(TenderDocument)
admin.site.register(DocumentChunk)
admin.site.register(MyTender)
admin.site.register(TenderDecision)
admin.site.register(ExecutionActivity)
admin.site.register(ExecutionWorkflowTemplate)
admin.site.register(TenderExecution)