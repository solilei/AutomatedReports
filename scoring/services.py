from audit import actions
from audit.service import log

from .attributes import ATTRIBUTES, ATTRIBUTE_FIELDS
from .models import CadetScore, ScoreSet

COMMENT_MAX_LENGTH = 1000
VALID_SCORES = {"1", "2", "3", "4", "5"}


def parse_submission(post, cadets):
    """Read the grid POST for the given cadets.

    Returns (data, errors). data maps cadet pk to {"scores": {field: int | None},
    "raw": {field: str}, "comment": str}.
    """
    data = {}
    errors = []
    for cadet in cadets:
        scores, raw = {}, {}
        for field, label, _header in ATTRIBUTES:
            value = post.get(f"s-{cadet.pk}-{field}", "")
            raw[field] = value
            if value == "":
                scores[field] = None
            elif value in VALID_SCORES:
                scores[field] = int(value)
            else:
                scores[field] = None
                errors.append(f"Invalid score for {cadet.name} / {label}.")
        comment = post.get(f"c-{cadet.pk}", "").strip()
        if len(comment) > COMMENT_MAX_LENGTH:
            errors.append(f"Comment for {cadet.name} is longer than {COMMENT_MAX_LENGTH} characters.")
        data[cadet.pk] = {"scores": scores, "raw": raw, "comment": comment}
    return data, errors


def count_blanks(data):
    """Return (blank_cells, blank_cadets, scored_cells)."""
    blank_cells = blank_cadets = scored_cells = 0
    for entry in data.values():
        blanks = sum(1 for v in entry["scores"].values() if v is None)
        blank_cells += blanks
        blank_cadets += 1 if blanks else 0
        scored_cells += len(entry["scores"]) - blanks
    return blank_cells, blank_cadets, scored_cells


def save_score_set(instructor, subject, group, data):
    """Create or update the instructor's score set. Call inside transaction.atomic()."""
    score_set, _ = ScoreSet.objects.get_or_create(
        instructor=instructor, subject=subject, group=group
    )
    labels = {field: label for field, label, _header in ATTRIBUTES}
    for cadet in group.cadets.filter(is_active=True):
        entry = data[cadet.pk]
        row, _ = CadetScore.objects.get_or_create(score_set=score_set, cadet=cadet)
        for field in ATTRIBUTE_FIELDS:
            old, new = getattr(row, field), entry["scores"][field]
            if old == new:
                continue
            setattr(row, field, new)
            log(
                instructor,
                actions.SCORE_CHANGED,
                f"{instructor.username} changed {labels[field]} for {cadet.name} "
                f"({subject.name}): {old or 'blank'} → {new or 'blank'}",
                group_number=group.number,
                details={
                    "cadet_id": cadet.pk,
                    "cadet": cadet.name,
                    "subject": subject.name,
                    "attribute": field,
                    "old": old,
                    "new": new,
                    "score_set_id": score_set.pk,
                },
            )
        old_comment = row.comment
        if old_comment != entry["comment"]:
            row.comment = entry["comment"]
            log(
                instructor,
                actions.COMMENT_CHANGED,
                f"{instructor.username} changed the comment for {cadet.name} ({subject.name})",
                group_number=group.number,
                details={
                    "cadet_id": cadet.pk,
                    "cadet": cadet.name,
                    "subject": subject.name,
                    "old": old_comment,
                    "new": entry["comment"],
                    "score_set_id": score_set.pk,
                },
            )
        row.save()
    score_set.save()
    return score_set
