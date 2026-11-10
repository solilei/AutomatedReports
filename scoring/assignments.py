from django.db import transaction

from audit import actions
from audit.service import log


def _details(user, subject):
    return {"username": user.username, "programme": subject.programme.name, "subject": subject.name}


def set_assignments(actor, user, subjects):
    """Make `subjects` the user's assigned subjects and log each addition and removal."""
    wanted = {s.pk: s for s in subjects}
    with transaction.atomic():
        current = {s.pk: s for s in user.assigned_subjects.select_related("programme")}
        for pk in sorted(set(wanted) - set(current)):
            subject = wanted[pk]
            subject.instructors.add(user)
            log(
                actor,
                actions.SUBJECT_ASSIGNED,
                f"{subject.name} ({subject.programme.name}) assigned to {user.username}",
                details=_details(user, subject),
            )
        for pk in sorted(set(current) - set(wanted)):
            subject = current[pk]
            subject.instructors.remove(user)
            log(
                actor,
                actions.SUBJECT_UNASSIGNED,
                f"{subject.name} ({subject.programme.name}) unassigned from {user.username}",
                details=_details(user, subject),
            )
