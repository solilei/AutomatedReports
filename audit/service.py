from audit import actions
from audit.actions import ALL_ACTIONS
from audit.models import AuditEvent

SUMMARY_MAX_LENGTH = 500

# Events whose summary or details name a cadet or hold their scores or comments.
CADET_DATA_ACTIONS = [
    actions.CADET_ADDED,
    actions.CADET_RENAMED,
    actions.CADET_DEACTIVATED,
    actions.CADET_REACTIVATED,
    actions.CADET_DELETED,
    actions.SCORE_CHANGED,
    actions.COMMENT_CHANGED,
]


def redact_group(group_number):
    """Strip cadet data from a deleted group's events; who, what and when stay.

    This is the one sanctioned edit of audit events, so it uses a queryset update,
    which skips AuditEvent.save's immutability check.
    """
    events = AuditEvent.objects.filter(group_number=group_number, action__in=CADET_DATA_ACTIONS)
    return events.update(
        summary=f"Details removed when group {group_number} was deleted",
        details={"redacted": True},
    )


def log(actor, action, summary, *, group_number="", details=None, actor_label=None):
    if action not in ALL_ACTIONS:
        raise ValueError(f"Unknown audit action: {action!r}")
    if actor_label is None:
        actor_label = actor.username if actor is not None else "system"
    return AuditEvent.objects.create(
        actor=actor,
        actor_label=actor_label,
        action=action,
        group_number=group_number,
        summary=summary[:SUMMARY_MAX_LENGTH],
        details=details if details is not None else {},
    )
