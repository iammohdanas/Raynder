from django.urls import include, path
from . import views

urlpatterns = [
    path("", views.index, name="main"),
    path("home/", views.index, name="home"),
    path("tenders/", views.tender_list_page, name="tender_list"),
    path("tenders/<int:tender_id>/", views.tender_detail_page, name="tender-detail-page"),
    path("tenders/create/", views.create_tender_page,name="create_tender_page"),
]
