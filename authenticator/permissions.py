
from collections import defaultdict

from authenticator.models import Profile


def get_employee_profile(user):
    """Return the user's Profile, or None if it does not exist."""
    if not user or not getattr(user, "is_authenticated", False):
        return None

    return (
        Profile.objects
        .select_related("user", "reporting_manager")
        .filter(user_id=user.pk)
        .first()
    )


def is_system_admin(user):
    """
    System-wide access:
    - Django superusers
    - Approved Level 5 employee accounts
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if user.is_superuser:
        return True

    profile = get_employee_profile(user)

    return bool(
        profile
        and profile.account_type == "EMPLOYEE"
        and profile.approval_status == "APPROVED"
        and profile.level == 5
    )


def is_approved_employee(user):
    """Check whether a user is an active, approved employee."""
    profile = get_employee_profile(user)

    return bool(
        profile
        and user.is_active
        and profile.account_type == "EMPLOYEE"
        and profile.approval_status == "APPROVED"
        and profile.level in (1, 2, 3, 4, 5)
    )


def get_approved_employee_profiles():
    """Get all active and approved employee profiles."""
    return Profile.objects.filter(
        account_type="EMPLOYEE",
        approval_status="APPROVED",
        user__is_active=True,
        level__in=(1, 2, 3, 4, 5),
    ).select_related(
        "user",
        "reporting_manager",
        "reporting_manager__user",
    )


def get_reporting_tree_profiles(user, include_self=False):
    """
    Return all approved employees below the given user
    in the reporting hierarchy.

    Uses an in-memory traversal to avoid one database query
    for every level of the hierarchy.
    """
    if is_system_admin(user):
        profiles = list(get_approved_employee_profiles())

        if include_self:
            return profiles

        return [
            profile for profile in profiles
            if profile.user_id != user.pk
        ]

    manager_profile = get_employee_profile(user)

    if not is_approved_employee(user) or not manager_profile:
        return []

    all_profiles = list(get_approved_employee_profiles())

    # Build manager -> direct reports mapping.
    children_map = defaultdict(list)

    for profile in all_profiles:
        if profile.reporting_manager_id:
            children_map[profile.reporting_manager_id].append(profile)

    # Traverse all descendants.
    descendants = []
    visited = {manager_profile.pk}
    pending = [manager_profile.pk]

    while pending:
        current_manager_id = pending.pop(0)

        for employee in children_map.get(current_manager_id, []):
            if employee.pk in visited:
                continue

            visited.add(employee.pk)
            descendants.append(employee)
            pending.append(employee.pk)

    if include_self:
        return [manager_profile] + descendants

    return descendants


def get_visible_employee_profiles(user):
    """
    Return the employees visible to the logged-in user.

    Admin: all approved employees.
    Employee: self and entire reporting tree.
    """
    if is_system_admin(user):
        return list(get_approved_employee_profiles())

    if not is_approved_employee(user):
        return []

    return get_reporting_tree_profiles(user, include_self=True)


def can_view_employee(actor, target_user):
    """Check whether actor can view the target employee's data."""
    if not is_approved_employee(target_user):
        return False

    if is_system_admin(actor):
        return True

    if not is_approved_employee(actor):
        return False

    visible_ids = {
        profile.user_id
        for profile in get_visible_employee_profiles(actor)
    }

    return target_user.pk in visible_ids



def can_assign_to_employee(actor, target_user):
    """
    Assignment rules:

    Level 1:
        Cannot assign tasks.

    Level 2 - Manager:
        Can assign to:
        - Themselves.
        - Employees in their own reporting tree.
        - Parallel managers reporting to the same HOD.

    Level 3 - HOD:
        Can assign to:
        - Themselves.
        - Everyone in their reporting tree.
        - Parallel HODs reporting to the same MD.
        Cannot directly assign to employees under another HOD.

    Level 4 - MD:
        Can assign to any approved employee.

    Level 5 / Superuser:
        Unrestricted assignment.
    """

    # Target must be an active, approved employee.
    if not is_approved_employee(target_user):
        return False

    # Admin and superuser have unrestricted access.
    if is_system_admin(actor):
        return True

    if not is_approved_employee(actor):
        return False

    actor_profile = get_employee_profile(actor)
    target_profile = get_employee_profile(target_user)

    if not actor_profile or not target_profile:
        return False

    actor_level = actor_profile.level

    # Level 1 cannot assign tasks.
    if actor_level == 1:
        return False

    # MD can assign to anyone in the organization.
    if actor_level == 4:
        return True

    if actor_level not in (2, 3):
        return False

    # Self-assignment is allowed for Managers and HODs.
    if actor.pk == target_user.pk:
        return True

    # Anyone in the actor's own reporting tree is accessible.
    reporting_tree_ids = {
        profile.user_id
        for profile in get_reporting_tree_profiles(
            actor,
            include_self=False,
        )
    }

    if target_user.pk in reporting_tree_ids:
        return True

    # Parallel assignment:
    # Managers can assign to peer managers under the same HOD.
    # HODs can assign to peer HODs under the same MD.
    same_level_peer = (
        actor_level == target_profile.level
        and actor_profile.reporting_manager_id is not None
        and actor_profile.reporting_manager_id
            == target_profile.reporting_manager_id
    )

    return same_level_peer
