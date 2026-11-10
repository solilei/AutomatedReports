from django.http import Http404
from django.shortcuts import get_object_or_404

from roster.models import Group


def get_visible_group(request, number):
    group = get_object_or_404(Group, number=number)
    if not request.user.is_admin:
        if group.status == Group.Status.ARCHIVED:
            raise Http404
        if not assigned_subjects(request.user, group.programme):
            raise Http404
    return group


def assigned_subjects(user, programme, active_only=False):
    """The subjects assigned to this user in this programme."""
    from .models import Subject

    subjects = Subject.objects.filter(programme=programme, instructors=user)
    if active_only:
        subjects = subjects.filter(is_active=True)
    return list(subjects)


def can_score(user, group, subject):
    """A user scores a subject only when it is in the group's programme and assigned to
    them. Admins follow the same rule."""
    return (
        subject.programme_id == group.programme_id
        and subject.instructors.filter(pk=user.pk).exists()
    )


def can_view_score_set(user, score_set):
    """Admins see every score set. An instructor sees a colleague's score set when they
    are assigned the same subject and the group is not archived; their own sets are
    viewed and edited on the scoring page."""
    if user.is_admin:
        return True
    if score_set.instructor_id == user.pk or score_set.group.status == Group.Status.ARCHIVED:
        return False
    return score_set.subject.instructors.filter(pk=user.pk).exists()
