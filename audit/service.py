from audit.actions import ALL_ACTIONS
from audit.models import AuditEvent

SUMMARY_MAX_LENGTH = 500


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
