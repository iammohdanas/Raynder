
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
    path(
        "chat/conversations/<uuid:conversation_id>/messages/",
        views.send_message,
        name="chat_send_message",
    ),
]
