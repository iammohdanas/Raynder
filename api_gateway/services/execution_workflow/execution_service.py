
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction

from api_gateway.models import (
    MyTender,
    TenderExecution,
    ExecutionWorkflowTemplate,
    ExecutionActivity,
)
from django.contrib.auth import get_user_model
import os
import uuid

from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction

def validate_dependency_graph(tasks_by_code):
    """
    Validate dependency references and prevent circular dependencies.
    """
    visited = set()
    visiting = set()

    def visit(task_code):
        if task_code in visiting:
            raise ValidationError(
                f"Circular dependency detected involving: {task_code}"
            )

        if task_code in visited:
            return

        visiting.add(task_code)

        task = tasks_by_code[task_code]

        for dependency in task.get("dependencies", []):
            if dependency not in tasks_by_code:
                raise ValidationError(
                    f"Unknown dependency '{dependency}' "
                    f"referenced by task '{task_code}'."
                )

            if dependency == task_code:
                raise ValidationError(
                    f"Task '{task_code}' cannot depend on itself."
                )

            visit(dependency)

        visiting.remove(task_code)
        visited.add(task_code)

    for task_code in tasks_by_code:
        visit(task_code)


@transaction.atomic
def create_execution_plan(my_tender, created_by=None):

    # Lock the MyTender record to prevent concurrent plan creation.
    my_tender = (
        MyTender.objects
        .select_for_update()
        .select_related("tender")
        .get(pk=my_tender.pk)
    )

    # Only GO-approved tenders can start execution.
    if my_tender.status != MyTender.Status.GO_APPROVED:
        raise ValidationError(
            "Execution plan can only be generated for GO-approved tenders."
        )

    # Prevent duplicate execution plans.
    existing = TenderExecution.objects.filter(
        my_tender=my_tender
    ).first()

    if existing:
        return existing, False

    # Get the latest active workflow template.
    template = (
        ExecutionWorkflowTemplate.objects
        .filter(is_active=True)
        .order_by("-version", "-id")
        .first()
    )

    if not template:
        raise ValidationError(
            "No active execution workflow template found."
        )

    template_phases = template.workflow_data.get("phases", [])

    if not template_phases:
        raise ValidationError(
            "Workflow template does not contain any phases."
        )

    # First pass: collect all tasks and generate UUIDs.
    tasks_by_code = {}
    task_id_map = {}

    for phase in template_phases:

        for task in phase.get("tasks", []):

            code = task.get("code")

            if not code:
                raise ValidationError(
                    "Every workflow task must have a unique code."
                )

            if code in tasks_by_code:
                raise ValidationError(
                    f"Duplicate task code found: {code}"
                )

            if not task.get("title"):
                raise ValidationError(
                    f"Task '{code}' is missing its title."
                )

            tasks_by_code[code] = task
            task_id_map[code] = str(uuid.uuid4())

    if not tasks_by_code:
        raise ValidationError("Workflow contains no tasks.")

    # Validate all dependencies before generating the plan.
    validate_dependency_graph(tasks_by_code)

    # Second pass: create the execution snapshot.
    execution_phases = []

    for phase in template_phases:

        execution_tasks = []

        for task in phase.get("tasks", []):

            code = task["code"]

            is_optional = task.get("optional", False)
            condition = task.get("condition")

            dependencies = [
                task_id_map[dependency]
                for dependency in task.get("dependencies", [])
            ]

            # Conditional/optional tasks require an applicability decision.
            # They must not automatically become NOT_APPLICABLE.
            is_applicable = (
                None if is_optional or condition else True
            )

            execution_tasks.append({
                "id": task_id_map[code],
                "code": code,
                "title": task["title"],
                "description": task.get("description", ""),

                "status": "PENDING",

                "department": task.get("department", ""),
                "priority": task.get("priority", "MEDIUM"),

                "optional": is_optional,
                "condition": condition,
                "is_applicable": is_applicable,

                "assignees": [],

                "dependencies": dependencies,

                "start_date": None,
                "due_date": None,
                "completed_at": None,

                "remarks": "",
                "comments": [],
                "attachments": [],

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

    # Complete execution snapshot.
    workflow_data = {
        "schema_version": 1,
        "template_version": template.version,
        "phases": execution_phases,
    }

    # Create the execution plan.
    execution = TenderExecution.objects.create(
        my_tender=my_tender,
        template=template,
        workflow_data=workflow_data,
        overall_progress=0,
        created_by=created_by,
    )

    # Record the plan creation in the activity log.
    ExecutionActivity.objects.create(
        execution=execution,
        activity_type="PLAN_CREATED",
        description="Tender execution workflow plan generated.",
        metadata={
            "template_id": template.id,
            "template_name": template.name,
            "template_version": template.version,
            "phase_count": len(execution_phases),
            "task_count": len(tasks_by_code),
        },
        performed_by=created_by,
    )

    return execution, True


@transaction.atomic
def set_task_applicability(
    execution_id,
    task_id,
    is_applicable,
    performed_by=None,
    remarks="",
):
    """
    Update whether an optional or conditional task applies.

    is_applicable:
        True  -> PENDING
        False -> NOT_APPLICABLE
        None  -> Undecided (PENDING)
    """

    if is_applicable not in (True, False, None):
        raise ValidationError(
            "is_applicable must be True, False, or None."
        )

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    workflow_data = execution.workflow_data
    task_found = None

    # Find the task using its UUID.
    for phase in workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("id") == str(task_id):
                task_found = task
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError("Task not found in this execution plan.")

    # Only optional or conditional tasks can have applicability changed.
    if not (
        task_found.get("optional", False)
        or task_found.get("condition")
    ):
        if is_applicable is not True:
            raise ValidationError(
                "Mandatory tasks cannot be marked as not applicable "
                "or undecided."
            )

    current_status = task_found.get("status", "PENDING")

    # Do not modify tasks on which work has already started.
    if current_status not in ("PENDING", "NOT_APPLICABLE"):
        raise ValidationError(
            "Applicability cannot be changed after a task has started "
            "or been completed."
        )

    old_applicability = task_found.get("is_applicable")

    new_status = (
        "NOT_APPLICABLE"
        if is_applicable is False
        else "PENDING"
    )

    # Avoid unnecessary database writes and activity records.
    if (
        old_applicability is is_applicable
        and current_status == new_status
    ):
        return execution, False

    task_found["is_applicable"] = is_applicable
    task_found["status"] = new_status

    workflow_data["phases"] = workflow_data.get("phases", [])

    execution.workflow_data = workflow_data
    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    # Record the change.
    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="TASK_APPLICABILITY_CHANGED",
        description=(
            f"Task '{task_found.get('title')}' applicability changed."
        ),
        metadata={
            "task_code": task_found.get("code"),
            "old_applicability": old_applicability,
            "new_applicability": is_applicable,
            "old_status": current_status,
            "new_status": new_status,
            "remarks": remarks,
        },
        performed_by=performed_by,
    )

    return execution, True



@transaction.atomic
def add_custom_task(
    execution_id,
    phase_code,
    title,
    description="",
    department="",
    priority="MEDIUM",
    due_date=None,
    dependencies=None,
    created_by=None,
):
    """
    Add a custom task to an existing execution phase.
    """

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    if not title or not title.strip():
        raise ValidationError("Task title is required.")

    allowed_priorities = {"LOW", "MEDIUM", "HIGH", "URGENT"}

    if priority not in allowed_priorities:
        raise ValidationError("Invalid task priority.")

    workflow_data = execution.workflow_data
    phases = workflow_data.get("phases", [])

    phase = next(
        (
            item for item in phases
            if item.get("code") == phase_code
        ),
        None
    )

    if not phase:
        raise ValidationError("Execution phase not found.")

    dependencies = dependencies or []

    # Collect existing task IDs and validate dependencies.
    all_tasks = [
        task
        for item in phases
        for task in item.get("tasks", [])
    ]

    task_id_map = {
        task.get("id"): task
        for task in all_tasks
    }

    for dependency_id in dependencies:
        dependency = task_id_map.get(str(dependency_id))

        if not dependency:
            raise ValidationError(
                f"Dependency task '{dependency_id}' was not found."
            )

        if dependency.get("status") == "NOT_APPLICABLE":
            raise ValidationError(
                "Cannot add a dependency on a task marked not applicable."
            )

    # Generate a unique task code.
    custom_task_number = 1

    existing_codes = {
        task.get("code")
        for task in all_tasks
    }

    while f"CUSTOM_{custom_task_number:03d}" in existing_codes:
        custom_task_number += 1

    task_id = str(uuid.uuid4())

    custom_task = {
        "id": task_id,
        "code": f"CUSTOM_{custom_task_number:03d}",
        "title": title.strip(),
        "description": description.strip(),
        "status": "PENDING",
        "department": department,
        "priority": priority,
        "optional": False,
        "condition": None,
        "is_applicable": True,
        "assignees": [],
        "dependencies": [str(item) for item in dependencies],
        "start_date": None,
        "due_date": str(due_date) if due_date else None,
        "completed_at": None,
        "remarks": "",
        "comments": [],
        "attachments": [],
        "approval_required": False,
        "approvals": [],
        "is_custom": True,
    }

    phase.setdefault("tasks", []).append(custom_task)

    execution.workflow_data = workflow_data
    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=task_id,
        activity_type="CUSTOM_TASK_CREATED",
        description=f"Custom task '{title.strip()}' created.",
        metadata={
            "task_code": custom_task["code"],
            "phase_code": phase_code,
            "phase_name": phase.get("name"),
            "priority": priority,
            "dependencies": dependencies,
        },
        performed_by=created_by,
    )

    return execution, custom_task


@transaction.atomic
def update_custom_task(
    execution_id,
    task_id,
    title,
    description="",
    department="",
    priority="MEDIUM",
    due_date=None,
    dependencies=None,
    updated_by=None,
):
    """
    Update an existing custom task in an execution plan.
    """

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    workflow_data = execution.workflow_data
    phases = workflow_data.get("phases", [])

    task = None
    target_phase = None

    for phase in phases:
        for item in phase.get("tasks", []):
            if str(item.get("id")) == str(task_id):
                task = item
                target_phase = phase
                break

        if task:
            break

    if not task:
        raise ValidationError("Task not found.")

    if not task.get("is_custom"):
        raise ValidationError(
            "Only custom tasks can be edited."
        )

    if not title or not title.strip():
        raise ValidationError("Task title is required.")

    allowed_priorities = {"LOW", "MEDIUM", "HIGH", "URGENT"}

    if priority not in allowed_priorities:
        raise ValidationError("Invalid task priority.")

    dependencies = dependencies or []

    all_tasks = [
        item
        for phase in phases
        for item in phase.get("tasks", [])
    ]

    task_id_map = {
        str(item.get("id")): item
        for item in all_tasks
    }

    normalized_dependencies = []

    for dependency_id in dependencies:
        dependency_id = str(dependency_id)

        if dependency_id == str(task_id):
            raise ValidationError(
                "A task cannot depend on itself."
            )

        dependency = task_id_map.get(dependency_id)

        if not dependency:
            raise ValidationError(
                f"Dependency task '{dependency_id}' was not found."
            )

        if dependency.get("status") == "NOT_APPLICABLE":
            raise ValidationError(
                "Cannot add a dependency on a task marked not applicable."
            )

        if dependency_id not in normalized_dependencies:
            normalized_dependencies.append(dependency_id)

    # Validate dependency graph before saving.
    tasks_by_code = {
        item["code"]: item
        for item in all_tasks
        if item.get("code")
    }

    dependency_graph = {}

    for item in all_tasks:
        code = item.get("code")
        if not code:
            continue

        dependency_codes = []

        for dependency_id in (
            normalized_dependencies
            if str(item.get("id")) == str(task_id)
            else item.get("dependencies", [])
        ):
            dependency = task_id_map.get(str(dependency_id))

            if dependency:
                dependency_codes.append(dependency["code"])

        dependency_graph[code] = dependency_codes

    validate_dependency_graph(dependency_graph)

    old_values = {
        "title": task.get("title"),
        "description": task.get("description"),
        "department": task.get("department"),
        "priority": task.get("priority"),
        "due_date": task.get("due_date"),
        "dependencies": task.get("dependencies", []),
    }

    task.update({
        "title": title.strip(),
        "description": description.strip(),
        "department": department,
        "priority": priority,
        "due_date": str(due_date) if due_date else None,
        "dependencies": normalized_dependencies,
    })

    execution.workflow_data = workflow_data
    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="CUSTOM_TASK_UPDATED",
        description=f"Custom task '{task['title']}' updated.",
        metadata={
            "task_code": task.get("code"),
            "phase_code": target_phase.get("code"),
            "old_values": old_values,
            "new_values": {
                "title": task["title"],
                "description": task["description"],
                "department": task["department"],
                "priority": task["priority"],
                "due_date": task["due_date"],
                "dependencies": normalized_dependencies,
            },
        },
        performed_by=updated_by,
    )

    return execution, task



@transaction.atomic
def set_task_assignees(
    execution_id,
    task_id,
    assignee_ids=None,
    due_date=None,
    update_due_date=False,
    performed_by=None,
):
    """
    Update execution task assignees and/or due date.

    Both operations work independently.
    Existing assignments remain unchanged when assignee_ids is None.
    """

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    normalized_ids = None

    # Validate assignees only when they are provided.
    if assignee_ids is not None:

        if not isinstance(assignee_ids, (list, tuple)):
            raise ValidationError(
                "Assignee IDs must be provided as a list."
            )

        normalized_ids = list(dict.fromkeys(
            str(user_id).strip()
            for user_id in assignee_ids
            if user_id is not None and str(user_id).strip()
        ))

        User = get_user_model()

        users = User.objects.filter(
            pk__in=normalized_ids
        )

        existing_ids = {
            str(user.pk)
            for user in users
        }

        invalid_ids = [
            user_id
            for user_id in normalized_ids
            if user_id not in existing_ids
        ]

        if invalid_ids:
            raise ValidationError(
                f"Invalid user IDs: {', '.join(invalid_ids)}"
            )

    # Find task.
    task_found = None

    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                task_found = task
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError(
            "Task not found in this execution plan."
        )

    if task_found.get("status") == "NOT_APPLICABLE":
        raise ValidationError(
            "Cannot update a task marked not applicable."
        )

    if task_found.get("is_applicable") is False:
        raise ValidationError(
            "Cannot update a task that is not applicable."
        )

    old_assignees = task_found.get("assignees", [])
    old_due_date = task_found.get("due_date")

    # Check whether assignments actually changed.
    assignees_changed = (
        normalized_ids is not None
        and old_assignees != normalized_ids
    )

    # Check whether due date actually changed.
    new_due_date = str(due_date) if due_date else None

    due_date_changed = (
        update_due_date
        and old_due_date != new_due_date
    )

    # Nothing changed: return successfully without duplicate activity.
    if not assignees_changed and not due_date_changed:
        return execution, False

    # Update only the requested fields.
    if assignees_changed:
        task_found["assignees"] = normalized_ids

    if due_date_changed:
        task_found["due_date"] = new_due_date

    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    # Record assignment activity only when assignments changed.
    if assignees_changed:
        ExecutionActivity.objects.create(
            execution=execution,
            task_id=str(task_id),
            activity_type="TASK_ASSIGNED",
            description=(
                f"Assignees updated for task "
                f"'{task_found.get('title')}'."
            ),
            metadata={
                "task_code": task_found.get("code"),
                "previous_assignees": old_assignees,
                "new_assignees": normalized_ids,
            },
            performed_by=performed_by,
        )

    # Record due-date activity only when due date changed.
    if due_date_changed:
        ExecutionActivity.objects.create(
            execution=execution,
            task_id=str(task_id),
            activity_type="TASK_DUE_DATE_UPDATED",
            description=(
                f"Due date updated for task "
                f"'{task_found.get('title')}'."
            ),
            metadata={
                "task_code": task_found.get("code"),
                "previous_due_date": old_due_date,
                "new_due_date": new_due_date,
            },
            performed_by=performed_by,
        )

    return execution, True


@transaction.atomic
def update_task_status(
    execution_id,
    task_id,
    new_status,
    performed_by=None,
    remarks="",
):
    """
    Update an execution task's status with dependency validation.
    """

    allowed_statuses = {
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "BLOCKED",
    }

    if new_status not in allowed_statuses:
        raise ValidationError(
            f"Invalid task status. Allowed statuses: "
            f"{', '.join(sorted(allowed_statuses))}"
        )

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    workflow_data = execution.workflow_data
    phases = workflow_data.get("phases", [])

    # Locate the task and build a task lookup.
    task_map = {}
    task_found = None

    for phase in phases:
        for task in phase.get("tasks", []):
            task_map[str(task.get("id"))] = task

            if str(task.get("id")) == str(task_id):
                task_found = task

    if not task_found:
        raise ValidationError("Task not found in this execution plan.")

    current_status = task_found.get("status", "PENDING")

    if current_status == "NOT_APPLICABLE":
        raise ValidationError(
            "Cannot update a task marked not applicable. "
            "Change its applicability first."
        )

    if task_found.get("is_applicable") is False:
        raise ValidationError(
            "Cannot update a task that is not applicable."
        )

    if current_status == new_status:
        return execution, False

    # Validate dependencies before starting or completing a task.
    if new_status in {"IN_PROGRESS", "COMPLETED"}:

        for dependency_id in task_found.get("dependencies", []):

            dependency = task_map.get(str(dependency_id))

            if not dependency:
                raise ValidationError(
                    f"Dependency task '{dependency_id}' was not found."
                )

            dependency_status = dependency.get("status", "PENDING")

            # NOT_APPLICABLE counts as a satisfied dependency.
            if dependency_status not in {
                "COMPLETED",
                "NOT_APPLICABLE",
            }:
                raise ValidationError(
                    f"Cannot update this task to {new_status}. "
                    f"Prerequisite '{dependency.get('title')}' "
                    f"is currently {dependency_status}."
                )

    old_status = current_status

    task_found["status"] = new_status

    # Manage completion timestamp.
    if new_status == "COMPLETED":
        task_found["completed_at"] = timezone.now().isoformat()
    else:
        task_found["completed_at"] = None

    # Update task remarks when provided.
    if remarks:
        task_found["remarks"] = remarks

    execution.workflow_data = workflow_data
    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    # Record the status change.
    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="TASK_STATUS_CHANGED",
        description=(
            f"Task '{task_found.get('title')}' status changed "
            f"from {old_status} to {new_status}."
        ),
        metadata={
            "task_code": task_found.get("code"),
            "old_status": old_status,
            "new_status": new_status,
            "remarks": remarks,
        },
        performed_by=performed_by,
    )

    return execution, True


@transaction.atomic
def add_task_comment(
    execution_id,
    task_id,
    comment,
    performed_by=None,
):
    """
    Add a comment to a task's discussion history.
    """

    if not comment or not comment.strip():
        raise ValidationError("Comment cannot be empty.")

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    task_found = None

    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                task_found = task
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError("Task not found.")
    
    profile = getattr(performed_by, "profile", None) if performed_by else None
    employee_name = (performed_by.get_full_name().strip() or performed_by.username if performed_by else "Unknown" )
    comment_data = {
        "id": str(uuid.uuid4()),
        "text": comment.strip(),
        "user_id": str(performed_by.pk) if performed_by else None,
        "employee_id": profile.employee_id if profile else None,
        "employee_name": employee_name,
        "created_at": timezone.now().isoformat(),
    }

    task_found.setdefault("comments", []).append(comment_data)

    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="TASK_COMMENT_ADDED",
        description=(
            f"Comment added to task '{task_found.get('title')}'."
        ),
        metadata={
            "task_code": task_found.get("code"),
            "comment_id": comment_data["id"],
        },
        performed_by=performed_by,
    )

    return execution, comment_data


@transaction.atomic
def update_task_remarks(
    execution_id,
    task_id,
    remarks,
    performed_by=None,
):
    """
    Update the latest remarks for an execution task.
    """

    if remarks is None:
        raise ValidationError("Remarks cannot be null.")

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    task_found = None

    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                task_found = task
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError("Task not found.")

    old_remarks = task_found.get("remarks", "")
    new_remarks = remarks.strip()

    if old_remarks == new_remarks:
        return execution, False

    task_found["remarks"] = new_remarks

    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="TASK_REMARKS_UPDATED",
        description=(
            f"Remarks updated for task '{task_found.get('title')}'."
        ),
        metadata={
            "task_code": task_found.get("code"),
            "old_remarks": old_remarks,
            "new_remarks": new_remarks,
        },
        performed_by=performed_by,
    )

    return execution, True




@transaction.atomic
def add_task_attachment(
    execution_id,
    task_id,
    uploaded_file,
    uploaded_by=None,
):
    """
    Upload a task attachment into its phase/task-specific folder.
    """

    if not uploaded_file:
        raise ValidationError("Please select a file.")

    MAX_FILE_SIZE = 20 * 1024 * 1024

    if uploaded_file.size > MAX_FILE_SIZE:
        raise ValidationError("Maximum file size allowed is 20 MB.")

    allowed_extensions = {
        ".pdf", ".doc", ".docx",
        ".xls", ".xlsx",
        ".png", ".jpg", ".jpeg",
        ".zip",
    }

    original_name = os.path.basename(uploaded_file.name)
    extension = os.path.splitext(original_name)[1].lower()

    if extension not in allowed_extensions:
        raise ValidationError("Unsupported attachment file type.")

    execution = (
        TenderExecution.objects
        .select_for_update()
        .select_related("my_tender")
        .get(pk=execution_id)
    )

    task_found = None
    phase_found = None

    # Identify both the phase and task.
    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                task_found = task
                phase_found = phase
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError("Task not found.")

    if task_found.get("status") == "NOT_APPLICABLE":
        raise ValidationError(
            "Cannot attach files to a task marked not applicable."
        )

    phase_code = phase_found.get("code")
    task_code = task_found.get("code")

    if not phase_code or not task_code:
        raise ValidationError(
            "Phase code or task code is missing."
        )

    attachment_id = str(uuid.uuid4())

    # Tender -> Execution -> Phase -> Task -> File
    storage_path = (
        f"tenders/{execution.my_tender.tender_id}/"
        f"executions/{phase_code}/{task_code}/"
        f"{attachment_id}{extension}"
    )

    saved_path = default_storage.save(
        storage_path,
        uploaded_file,
    )

    attachment_data = {
        "id": attachment_id,
        "original_filename": original_name,
        "file_path": saved_path,
        "file_size": uploaded_file.size,
        "extension": extension,
        "phase_code": phase_code,
        "task_code": task_code,
        "uploaded_by": (
            str(uploaded_by.pk) if uploaded_by else None
        ),
        "uploaded_at": timezone.now().isoformat(),
    }

    task_found.setdefault("attachments", []).append(
        attachment_data
    )

    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="TASK_ATTACHMENT_ADDED",
        description=(
            f"Attachment '{original_name}' uploaded to "
            f"'{task_found.get('title')}'."
        ),
        metadata={
            "attachment_id": attachment_id,
            "filename": original_name,
            "file_size": uploaded_file.size,
            "phase_code": phase_code,
            "task_code": task_code,
        },
        performed_by=uploaded_by,
    )

    return execution, attachment_data


@transaction.atomic
def delete_task_attachment(
    execution_id,
    task_id,
    attachment_id,
    deleted_by=None,
):
    """
    Remove an attachment from a task and delete its stored file.
    """

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    task_found = None

    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                task_found = task
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError("Task not found.")

    attachments = task_found.get("attachments", [])

    attachment = next(
        (
            item for item in attachments
            if item.get("id") == str(attachment_id)
        ),
        None,
    )

    if not attachment:
        raise ValidationError("Attachment not found.")

    file_path = attachment.get("file_path")

    task_found["attachments"] = [
        item for item in attachments
        if item.get("id") != str(attachment_id)
    ]

    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    # Delete the actual stored file.
    if file_path and default_storage.exists(file_path):
        default_storage.delete(file_path)

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="TASK_ATTACHMENT_DELETED",
        description=(
            f"Attachment '{attachment.get('original_filename')}' deleted."
        ),
        metadata={
            "attachment_id": str(attachment_id),
            "filename": attachment.get("original_filename"),
        },
        performed_by=deleted_by,
    )

    return execution, True



@transaction.atomic
def configure_task_approvers(
    execution_id,
    task_id,
    approver_ids,
    approval_mode="ALL",
    performed_by=None,
):
    """
    Configure approvers and start a new approval round.
    Previous approval history is preserved.
    """

    from django.contrib.auth import get_user_model

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    approval_mode = approval_mode.upper()

    if approval_mode not in {"ALL", "ANY"}:
        raise ValidationError("Approval mode must be ALL or ANY.")

    if not isinstance(approver_ids, (list, tuple)) or not approver_ids:
        raise ValidationError("At least one approver is required.")

    normalized_ids = list(dict.fromkeys(
        str(user_id).strip()
        for user_id in approver_ids
        if user_id is not None and str(user_id).strip()
    ))

    if not normalized_ids:
        raise ValidationError("At least one valid approver is required.")

    User = get_user_model()

    existing_ids = set(
        str(user_id)
        for user_id in User.objects.filter(
            pk__in=normalized_ids
        ).values_list("pk", flat=True)
    )

    invalid_ids = [
        user_id for user_id in normalized_ids
        if user_id not in existing_ids
    ]

    if invalid_ids:
        raise ValidationError(
            f"Invalid approver IDs: {', '.join(invalid_ids)}"
        )

    task_found = None

    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                task_found = task
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError("Task not found.")

    if (
        task_found.get("status") == "NOT_APPLICABLE"
        or task_found.get("is_applicable") is False
    ):
        raise ValidationError(
            "Cannot configure approval for a task that is not applicable."
        )

    if task_found.get("status") == "COMPLETED":
        raise ValidationError(
            "Cannot configure approval for an already completed task."
        )

    previous_round = task_found.get("approval_round", 0)
    current_round = previous_round + 1

    task_found.update({
        "approval_required": True,
        "approval_mode": approval_mode,
        "approver_ids": normalized_ids,
        "approval_round": current_round,
        "approval_status": "PENDING",
    })

    task_found.setdefault("approvals", [])

    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="APPROVAL_CONFIGURED",
        description=(
            f"Approval configured for task '{task_found.get('title')}'."
        ),
        metadata={
            "task_code": task_found.get("code"),
            "approver_ids": normalized_ids,
            "approval_mode": approval_mode,
            "approval_round": current_round,
        },
        performed_by=performed_by,
    )

    return execution, True


@transaction.atomic
def submit_task_approval(
    execution_id,
    task_id,
    decision,
    approver,
    remarks="",
):
    """
    Submit an approval or rejection decision.

    Only configured approvers can submit decisions.
    Each approver can decide once per approval round.
    """

    decision = decision.upper()

    if decision not in {"APPROVED", "REJECTED"}:
        raise ValidationError(
            "Decision must be APPROVED or REJECTED."
        )

    execution = (
        TenderExecution.objects
        .select_for_update()
        .get(pk=execution_id)
    )

    task_found = None

    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                task_found = task
                break

        if task_found:
            break

    if not task_found:
        raise ValidationError("Task not found.")

    if not task_found.get("approval_required"):
        raise ValidationError(
            "Approval is not required for this task."
        )

    if task_found.get("status") == "NOT_APPLICABLE":
        raise ValidationError(
            "Cannot approve a task marked not applicable."
        )

    if task_found.get("is_applicable") is False:
        raise ValidationError(
            "Cannot approve a task that is not applicable."
        )

    approval_status = task_found.get("approval_status")

    if approval_status != "PENDING":
        raise ValidationError(
            f"Approval is already {approval_status}."
        )

    approver_id = str(approver.pk)

    assigned_approvers = task_found.get("approver_ids", [])

    if approver_id not in assigned_approvers:
        raise ValidationError(
            "You are not an assigned approver for this task."
        )

    approval_round = task_found.get("approval_round", 1)

    approvals = task_found.setdefault("approvals", [])

    # Prevent duplicate decisions in the same approval round.
    already_decided = any(
        item.get("approver_id") == approver_id
        and item.get("round") == approval_round
        for item in approvals
    )

    if already_decided:
        raise ValidationError(
            "You have already submitted a decision for this round."
        )

    approval_record = {
        "id": str(uuid.uuid4()),
        "approver_id": approver_id,
        "decision": decision,
        "remarks": remarks.strip(),
        "round": approval_round,
        "decided_at": timezone.now().isoformat(),
    }

    approvals.append(approval_record)

    # Evaluate the current approval round.
    current_approvals = [
        item for item in approvals
        if item.get("round") == approval_round
    ]

    decisions = [
        item["decision"]
        for item in current_approvals
    ]

    approval_mode = task_found.get("approval_mode", "ALL")

    if approval_mode == "ALL":

        if "REJECTED" in decisions:
            new_approval_status = "REJECTED"

        elif (
            len(decisions) == len(assigned_approvers)
            and all(item == "APPROVED" for item in decisions)
        ):
            new_approval_status = "APPROVED"

        else:
            new_approval_status = "PENDING"

    else:  # ANY

        if "APPROVED" in decisions:
            new_approval_status = "APPROVED"

        elif len(decisions) == len(assigned_approvers):
            new_approval_status = "REJECTED"

        else:
            new_approval_status = "PENDING"

    task_found["approval_status"] = new_approval_status

    execution.save(
        update_fields=["workflow_data", "updated_at"]
    )

    ExecutionActivity.objects.create(
        execution=execution,
        task_id=str(task_id),
        activity_type="TASK_APPROVAL_DECISION",
        description=(
            f"{decision} decision submitted for "
            f"'{task_found.get('title')}'."
        ),
        metadata={
            "task_code": task_found.get("code"),
            "approver_id": approver_id,
            "decision": decision,
            "approval_mode": approval_mode,
            "approval_round": approval_round,
            "approval_status": new_approval_status,
            "remarks": remarks.strip(),
        },
        performed_by=approver,
    )

    return execution, new_approval_status


def calculate_execution_progress(execution):
    """
    Calculate overall and phase-wise execution progress.

    NOT_APPLICABLE and undecided optional/conditional tasks
    are excluded from the progress denominator.

    This function does not modify or save the execution.
    """

    phase_results = []

    overall_total = 0
    overall_completed = 0
    overall_undecided = 0
    overall_not_applicable = 0

    for phase in execution.workflow_data.get("phases", []):

        total_tasks = 0
        completed_tasks = 0
        undecided_tasks = 0
        not_applicable_tasks = 0

        for task in phase.get("tasks", []):

            status = task.get("status", "PENDING")

            # Explicitly excluded tasks.
            if (
                status == "NOT_APPLICABLE"
                or task.get("is_applicable") is False
            ):
                not_applicable_tasks += 1
                continue

            # Optional/conditional tasks awaiting applicability decision.
            if (
                task.get("is_applicable") is None
                and (
                    task.get("optional", False)
                    or task.get("condition")
                )
            ):
                undecided_tasks += 1
                continue

            total_tasks += 1

            if status == "COMPLETED":
                completed_tasks += 1

        phase_progress = (
            round((completed_tasks / total_tasks) * 100, 2)
            if total_tasks else 0
        )

        phase_results.append({
            "phase_code": phase.get("code"),
            "phase_name": phase.get("name"),
            "sequence": phase.get("sequence"),

            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": total_tasks - completed_tasks,

            "undecided_tasks": undecided_tasks,
            "not_applicable_tasks": not_applicable_tasks,

            "progress": phase_progress,
        })

        overall_total += total_tasks
        overall_completed += completed_tasks
        overall_undecided += undecided_tasks
        overall_not_applicable += not_applicable_tasks

    overall_progress = (
        round((overall_completed / overall_total) * 100, 2)
        if overall_total else 0
    )

    return {
        "overall_progress": overall_progress,

        "total_tasks": overall_total,
        "completed_tasks": overall_completed,
        "pending_tasks": overall_total - overall_completed,

        "undecided_tasks": overall_undecided,
        "not_applicable_tasks": overall_not_applicable,

        "phases_completed": sum(
            1 for phase in phase_results
            if phase["total_tasks"] > 0
            and phase["completed_tasks"] == phase["total_tasks"]
        ),

        "total_phases": len(phase_results),

        "phases": phase_results,
    }
