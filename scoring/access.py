from django.http import Http404
from django.shortcuts import get_object_or_404

from roster.models import Group


def get_visible_group(request, number):
    group = get_object_or_404(Group, number=number)
    if group.status == Group.Status.ARCHIVED and not request.user.is_admin:
        raise Http404
    return group


def scored_subjects(user, group):
    """Subjects this user has saved a score set for in this group."""
    from .models import Subject

    return list(Subject.objects.filter(scoreset__group=group, scoreset__instructor=user).distinct())


def can_view_score_set(user, score_set):
    """Admins see every score set. An instructor sees a colleague's score set when they
    have scored the same subject for the same (non-archived) group themselves; their own
    sets are viewed and edited on the scoring page."""
    from .models import ScoreSet

    if user.is_admin:
        return True
    if score_set.instructor_id == user.pk or score_set.group.status == Group.Status.ARCHIVED:
        return False
    return ScoreSet.objects.filter(
        instructor=user, group_id=score_set.group_id, subject_id=score_set.subject_id
    ).exists()
