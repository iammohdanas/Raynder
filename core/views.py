from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from api_gateway.models import MyTender
from authenticator.decorators import admin_required, role_required
from core.utils.blueprint_loader import load_workflow_blueprint
from django.contrib.auth.decorators import login_required


def index(request):
    return render(request, "index.html")


def sop_workflow(request):
    return render(request, "pages/sop_workflow.html")


@login_required
@admin_required
@role_required(['admin', 'manager'])
def create_project_page(request):
    return render(request, "pages/create_project.html")


@login_required
@role_required(['admin', 'manager','customer'])
def tender_list_page(request):
    return render(request, "pages/tender_list.html")

# @login_required
# @role_required(['admin', 'manager','customer'])
# def tender_detail_page(request, tender_id):
#     can_edit = (
#         request.user.is_superuser
#         or request.user.profile.role in ["admin", "manager"]
#     )
#     return render(request, "pages/tender_detail.html",
#         {
#             "tender_id": tender_id,
#             "can_edit": can_edit,
#         },
#     )

@login_required
@role_required(['admin', 'manager','customer'])
def tender_detail_page(request, tender_id):
    return render(request, "pages/tender_detail.html", {"tender_id": tender_id,},)

@login_required
@admin_required
@role_required(['admin', 'manager'])
def create_tender_page(request):
    return render(
        request,
        "pages/create_tender.html"
    )

@login_required
@role_required(['admin', 'manager'])
def priority_tenders_list_page(request):
    return render(request, "pages/priority_tenders.html")

@login_required
@admin_required
@role_required(["admin", "manager"])
def edit_tender_page(request, tender_id):
    return render(
        request,
        "pages/edit_tender.html",
        {
            "tender_id": tender_id,
        },
    )

@login_required
@role_required(['admin', 'manager', 'customer'])
def pq_analysis_page(request, tender_id):
    return render(
        request,
        "pages/pq_analysis.html",
        {
            "tender_id": tender_id,
        },
    )

@login_required
@role_required(['admin', 'manager', 'customer'])
def my_tenders_page(request):
    return render(
        request,
        "pages/my_tenders.html",
    )

@login_required
@role_required(['admin', 'manager', 'customer'])
def tender_execution_page(request, my_tender_id):
    my_tender = get_object_or_404(
        MyTender.objects.select_related("tender"),
        id=my_tender_id
    )
    return render(
        request,
        "pages/tender_execution.html",
        {
            "my_tender_id": my_tender.id,
            "tender_id": my_tender.tender.id,
        }
    )

@login_required
@role_required(['admin', 'manager', 'customer', 'staff'])
def my_tasks_page(request):
    return render(request, "task_management/my_tasks.html")


@login_required
@role_required(['admin', 'manager'])
def assigned_by_me_page(request):
    return render(request, "task_management/assigned_by_me.html")


@login_required
@role_required(['admin', 'manager'])
def team_tasks_page(request):
    return render(request, "task_management/team_tasks.html")


@login_required
@role_required(['admin'])
def all_tasks_page(request):
    return render(request, "task_management/all_tasks.html")