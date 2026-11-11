from collections import defaultdict
from dataclasses import dataclass

from accounts.models import User
from roster.models import Cadet, Group

from .models import CadetScore, CadetSubjectExclusion, ScoreSet, Subject


@dataclass(frozen=True)
class Gap:
    group: Group
    subject: Subject
    instructors: list[User]  # assigned instructors, any one of whom can fill the gap
    not_scored: bool  # True = nobody has saved a set for this subject in this group
    cadets: list  # not_scored: every cadet taking the subject; else cadets in no saved set


def missing_scores(groups=None, instructor=None) -> list[Gap]:
    """Subjects in active groups that no assigned instructor has scored.

    One saved set from any instructor covers the subject. A cadet is missing only when no
    saved set for the subject has a row for them. With `instructor`, only subjects assigned
    to that instructor are listed. Runs a fixed number of queries however many groups there are.
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

    # Active subjects with at least one active, approved assigned user.
    assignments = Subject.instructors.through.objects.filter(
        subject__programme_id__in=programme_ids,
        subject__is_active=True,
        user__is_active=True,
        user__is_approved=True,
    ).select_related("subject", "user")
    subjects = {}  # subject id -> subject
    instructors = defaultdict(list)  # subject id -> users
    for link in assignments:
        subjects[link.subject_id] = link.subject
        instructors[link.subject_id].append(link.user)
    if instructor is not None:
        subjects = {pk: s for pk, s in subjects.items() if instructor in instructors[pk]}
    by_programme = defaultdict(list)
    for subject in subjects.values():
        by_programme[subject.programme_id].append(subject)

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
    # Any saved set counts, whoever saved it.
    scored = set(
        ScoreSet.objects.filter(group__in=group_list).values_list("group_id", "subject_id")
    )
    covered = defaultdict(set)  # (group id, subject id) -> cadet ids with a row in some set
    for group_id, subject_id, cadet_id in CadetScore.objects.filter(
        score_set__group__in=group_list
    ).values_list("score_set__group_id", "score_set__subject_id", "cadet_id"):
        covered[(group_id, subject_id)].add(cadet_id)

    gaps = []
    for group in group_list:
        for subject in by_programme.get(group.programme_id, []):
            taking = [
                c for c in cadets_by_group[group.pk] if (c.pk, subject.pk) not in excluded
            ]
            if not taking:
                continue
            names = sorted(instructors[subject.pk], key=lambda u: u.display_name.casefold())
            key = (group.pk, subject.pk)
            if key not in scored:
                gaps.append(Gap(group, subject, names, True, taking))
                continue
            absent = [c for c in taking if c.pk not in covered[key]]
            if absent:
                gaps.append(Gap(group, subject, names, False, absent))
    gaps.sort(key=lambda g: (g.group.number, g.subject.name.casefold()))
    return gaps
