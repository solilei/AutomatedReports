from django.db import transaction

from audit import actions
from audit.service import log, redact_group

from .models import DeletedGroupNumber, Group, RosterUpload
from .services import OPEN_UPLOAD_STATUSES, discard_upload

Status = Group.Status

# action -> (statuses it may start from, new status, audit action, past tense)
TRANSITIONS = {
    "lock": ({Status.ACTIVE}, Status.LOCKED, actions.GROUP_LOCKED, "locked"),
    "unlock": ({Status.LOCKED}, Status.ACTIVE, actions.GROUP_UNLOCKED, "unlocked"),
    "archive": (
        {Status.ACTIVE, Status.LOCKED},
        Status.ARCHIVED,
        actions.GROUP_ARCHIVED,
        "archived",
    ),
    # Unarchive returns to status_before_archive; ACTIVE is the fallback.
    "unarchive": ({Status.ARCHIVED}, Status.ACTIVE, actions.GROUP_UNARCHIVED, "unarchived"),
}


def refusal(action, group):
    return f"Cannot {action} a group that is {group.status}."


def change_status(group, action, actor):
    """Apply a lock/unlock/archive/unarchive; return an error message or None."""
    allowed_from, new_status, audit_action, past = TRANSITIONS[action]
    with transaction.atomic():
        group = Group.objects.select_for_update().get(pk=group.pk)
        if group.status not in allowed_from:
            return refusal(action, group)
        if action == "archive":
            group.status_before_archive = group.status
        elif action == "unarchive":
            new_status = group.status_before_archive or new_status
            group.status_before_archive = ""
        group.status = new_status
        group.save(update_fields=["status", "status_before_archive"])
        log(
            actor,
            audit_action,
            f"{actor.username} {past} group {group.number}",
            group_number=group.number,
        )
    return None


def delete_group(group, actor):
    """Delete an archived group and its data; return an error message or None."""
    with transaction.atomic():
        group = Group.objects.select_for_update().get(pk=group.pk)
        if group.status != Status.ARCHIVED:
            return refusal("delete", group)
        details = {
            "cadets": group.cadets.count(),
            "score_sets": group.score_sets.count(),
        }
        DeletedGroupNumber.objects.create(number=group.number)
        # "All its data": unfinished uploads hold the whole roster file, and audit
        # events hold cadet names, scores and comments.
        open_uploads = RosterUpload.objects.select_for_update().filter(
            group_number=group.number, status__in=OPEN_UPLOAD_STATUSES
        )
        for upload in open_uploads:
            discard_upload(upload, actor, reason=f"group {group.number} was deleted")
        redact_group(group.number)
        log(
            actor,
            actions.GROUP_DELETED,
            f"{actor.username} deleted group {group.number}",
            group_number=group.number,
            details=details,
        )
        group.delete()
    return None
