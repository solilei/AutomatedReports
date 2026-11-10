from collections import defaultdict
from dataclasses import dataclass

from accounts.models import User
from roster.models import Cadet, Group

from .models import CadetScore, CadetSubjectExclusion, ScoreSet, Subject


@dataclass(frozen=True)
class Gap:
    group: Group
    subject: Subject
    instructor: User
    not_scored: bool  # True = no saved set
    cadets: list  # not_scored: every cadet taking the subject; else cadets with no row


def missing_scores(groups=None, instructor=None) -> list[Gap]:
    """Score sets that assigned instructors have not saved, in active groups.

    Runs a fixed number of queries however many groups there are.
    """
    group_list = [
        g
        for g in (
            groups if groups is not None else Group.objects.filter(status=Group.Status.ACTIVE)
        )
        if g.status == Group.Status.ACTIVE
    ]
    if not group_list:
        return []
    group_list = sorted(group_list, key=lambda g: g.number)
    programme_ids = {g.programme_id for g in group_list}

    # (subject, user) pairs for active subjects and active, approved users.
    assignments = Subject.instructors.through.objects.filter(
        subject__programme_id__in=programme_ids,
        subject__is_active=True,
        user__is_active=True,
        user__is_approved=True,
    ).select_related("subject", "user")
    if instructor is not None:
        assignments = assignments.filter(user=instructor)
    by_programme = defaultdict(list)
    for link in assignments:
        by_programme[link.subject.programme_id].append((link.subject, link.user))

    cadets_by_group = defaultdict(list)
    for cadet in Cadet.objects.filter(group__in=group_list, is_active=True).order_by(
        "position", "name"
    ):
        cadets_by_group[cadet.group_id].append(cadet)
    excluded = set(
        CadetSubjectExclusion.objects.filter(cadet__group__in=group_list).values_list(
            "cadet_id", "subject_id"
        )
    )
    set_ids = {
        (group_id, subject_id, instructor_id): set_id
        for set_id, group_id, subject_id, instructor_id in ScoreSet.objects.filter(
            group__in=group_list
        ).values_list("pk", "group_id", "subject_id", "instructor_id")
    }
    rows = defaultdict(set)
    for set_id, cadet_id in CadetScore.objects.filter(score_set__group__in=group_list).values_list(
        "score_set_id", "cadet_id"
    ):
        rows[set_id].add(cadet_id)

    gaps = []
    for group in group_list:
        for subject, user in by_programme.get(group.programme_id, []):
            taking = [
                c for c in cadets_by_group[group.pk] if (c.pk, subject.pk) not in excluded
            ]
            if not taking:
                continue
            set_id = set_ids.get((group.pk, subject.pk, user.pk))
            if set_id is None:
                gaps.append(Gap(group, subject, user, True, taking))
                continue
            absent = [c for c in taking if c.pk not in rows[set_id]]
            if absent:
                gaps.append(Gap(group, subject, user, False, absent))
    gaps.sort(
        key=lambda g: (
            g.group.number,
            g.subject.name.casefold(),
            g.instructor.display_name.casefold(),
        )
    )
    return gaps
