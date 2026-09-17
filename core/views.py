from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

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