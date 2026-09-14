from django.urls import path
from . import views

urlpatterns = [
    path('tendertiger/sync-tender/', views.sync_tenders, name='sync_tenders'),
    path('tenders/', views.get_tenders, name='get_tenders'),
    path("tenders/<int:tender_id>/",views.get_tender_detail,name="get-tender-detail"),
    path("tenders/create/", views.create_tender, name="create_tender"),
    path("priority-tenders-list/", views.get_priority_tenders, name="get_priority_tenders")
  ]
