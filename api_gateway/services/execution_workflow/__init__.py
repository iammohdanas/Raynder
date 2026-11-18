
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction

from api_gateway.models import (
    MyTender,
    TenderExecution,
    ExecutionWorkflowTemplate,
)


@transaction.atomic
def create_execution_plan(my_tender, created_by=None):
    """
    Generate a tender-specific execution plan from the
    active workflow template.

    Returns:
        (TenderExecution, created: bool)

    Safe to call multiple times for the same MyTender.
    """

    # Lock the parent to prevent concurrent plan creation.
    my_tender = MyTender.objects.select_for_update().get(
        pk=my_tender.pk
    )

    existing = TenderExecution.objects.filter(
        my_tender=my_tender
    ).first()

    if existing:
        return existing, False

    template = (
        ExecutionWorkflowTemplate.objects
        .filter(
            name="Raynder Standard Tender Execution",
            is_active=True,
        )
        .order_by("-version", "-id")
        .first()
    )

    if not template:
        raise ValidationError(
            "No active execution workflow template found."
        )

    template_phases = template.workflow_data.get("phases", [])

    if not template_phases:
        raise ValidationError("Workflow template has no phases.")

    # First pass: Generate unique IDs for every task.
    task_id_map = {}

    for phase in template_phases:
        for task in phase.get("tasks", []):
            code = task["code"]

            if code in task_id_map:
                raise ValidationError(
                    f"Duplicate task code: {code}"
                )

            task_id_map[code] = str(uuid.uuid4())

    execution_phases = []

    # Second pass: Build actual phases and tasks.
    for phase in template_phases:
        execution_tasks = []

        for task in phase.get("tasks", []):
            is_optional = task.get("optional", False)

            dependency_ids = []

            for dependency_code in task.get("dependencies", []):
                if dependency_code not in task_id_map:
                    raise ValidationError(
                        f"Unknown dependency: {dependency_code}"
                    )

                if dependency_code == task["code"]:
                    raise ValidationError(
                        "A task cannot depend on itself."
                    )

                dependency_ids.append(
                    task_id_map[dependency_code]
                )

            execution_tasks.append({
                "id": task_id_map[task["code"]],
                "code": task["code"],
                "title": task["title"],
                "description": task.get("description", ""),

                "department": task.get("department", ""),
                "priority": task.get("priority", "MEDIUM"),

                # Conditional tasks start inactive.
                "status": (
                    "NOT_APPLICABLE" if is_optional
                    else "PENDING"
                ),
                "optional": is_optional,
                "condition": task.get("condition"),
                "is_applicable": not is_optional,

                "assignees": [],
                "dependencies": dependency_ids,

                "start_date": None,
                "due_date": None,
                "completed_at": None,

                "remarks": "",
                "comments": [],
                "attachments": [],

                # Separate approval records within JSON.
                "approval_required": task.get(
                    "approval_required", False
                ),
                "approvals": [],

                "is_custom": False,
            })

        execution_phases.append({
            "code": phase["code"],
            "name": phase["name"],
            "sequence": phase["sequence"],
            "tasks": execution_tasks,
        })

    workflow_data = {
        "schema_version": 1,
        "template_version": template.version,
        "phases": execution_phases,
    }

    execution = TenderExecution.objects.create(
        my_tender=my_tender,
        template=template,
        workflow_data=workflow_data,
        overall_progress=0,
        created_by=created_by,
    )

    return execution, True
