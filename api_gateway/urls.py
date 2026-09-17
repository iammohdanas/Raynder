from django.urls import path
from . import views

urlpatterns = [
    path('tendertiger/sync-tender/', views.sync_tenders, name='sync_tenders'),
    path('tenders/', views.get_tenders, name='get_tenders'),
    path("tenders/<int:tender_id>/",views.get_tender_detail,name="get-tender-detail"),
    path("tenders/create/", views.create_tender, name="create_tender"),
    path("priority-tenders-list/", views.get_priority_tenders, name="get_priority_tenders"),
    path("tenders/<int:tender_id>/documents/", views.upload_tender_documents, name="upload_tender_documents"),
    path("tender-documents/<int:document_id>/", views.delete_tender_document, name="delete_tender_document"),
    path("tenders/<int:tender_id>/update/", views.update_tender, name="update_tender",),
]