
from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path(
        "chat/conversations/",
        views.conversations,
        name="chat_conversations",
    ),
    path(
        "chat/conversations/<uuid:conversation_id>/",
        views.conversation_detail,
        name="chat_conversation_detail",
    ),
    path("chat/conversations/<uuid:conversation_id>/messages/",views.send_message,name="chat_send_message",),
    
    path("evaluations/run/",views.start_rag_evaluation,name="start_rag_evaluation",),
    path("evaluations/<uuid:run_id>/",views.rag_evaluation_status,name="rag_evaluation_status",),
    path("evaluations/<uuid:run_id>/results/",views.rag_evaluation_results,name="rag_evaluation_results",),
    path("tenders/<str:tender_id>/run-pipeline/", views.start_document_pipeline, name="start_document_pipeline",),
    path("tasks/<str:task_id>/status/",views.document_pipeline_status,name="document_pipeline_status"),
    path("tenders/<int:tender_id>/pq-analysis/run/", views.start_pq_analysis, name="start_pq_analysis",),
    path("tasks/<str:task_id>/pq-analysis-status/", views.pq_analysis_task_status, name="pq_analysis_task_status",),
    path("tenders/<int:tender_id>/pq-analysis/latest/", views.get_latest_pq_analysis, name="get_latest_pq_analysis",),
]
