from django.urls import include, path
from . import views

urlpatterns = [
    path("", views.index, name="main"),
    path("home/", views.index, name="home"),
    path("tenders/", views.tender_list_page, name="tender_list"),
    path("tenders/<int:tender_id>/", views.tender_detail_page, name="tender-detail-page"),
    path("tenders/create/", views.create_tender_page,name="create_tender_page"),
    path("create-project/", views.create_project_page, name="create_project_page"),
    path("priority-tenders/", views.priority_tenders_list_page, name="priority_tenders_list"),
    path("tenders/<int:tender_id>/edit/", views.edit_tender_page,name="edit_tender_page",)
]
