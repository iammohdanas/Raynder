from django.urls import include, path
from . import views
from ai.views import download_tender_summary_excel

urlpatterns = [
    path("", views.index, name="main"),
    path("home/", views.index, name="home"),
    path("tenders/", views.tender_list_page, name="tender_list"),
    path("tenders/<int:tender_id>/", views.tender_detail_page, name="tender-detail-page"),
    path("tenders/create/", views.create_tender_page,name="create_tender_page"),
    path("create-project/", views.create_project_page, name="create_project_page"),
    path("priority-tenders/", views.priority_tenders_list_page, name="priority_tenders_list"),
    path("tenders/<int:tender_id>/edit/", views.edit_tender_page,name="edit_tender_page",),
    path("tenders/<int:tender_id>/pq-analysis/",views.pq_analysis_page,name="pq_analysis_page",),
    path("tenders/<int:tender_id>/summary/download/", download_tender_summary_excel, name="download_tender_summary_excel",),
    path("my-tenders/", views.my_tenders_page, name="my_tenders_page"),
    path("my-tenders/<int:my_tender_id>/execution/", views.tender_execution_page, name="tender_execution_page",),
    #task management system
    path("my-tasks/", views.my_tasks_page, name="my_tasks_page"),
    path("tasks/assigned-by-me/", views.assigned_by_me_page, name="assigned_by_me_page"),
    path("tasks/team/", views.team_tasks_page, name="team_tasks_page"),
    path("tasks/all/", views.all_tasks_page, name="all_tasks_page"),

]
