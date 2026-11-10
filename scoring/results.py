from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from roster.models import Cadet
from scoring.exclusions import excluded_pairs
from scoring.attributes import ATTRIBUTE_FIELDS, BLANK_COUNTS_AS
from scoring.models import ScoreSet

BAND_HEX = {5: "66FF33", 4: "C6E0B4", 3: "E2EFDA", 2: "FFC000", 1: "FF0000"}
FLAG_BELOW = 3  # a rounded average below C (3) is flagged


def round_average(total: int, count: int) -> int:
    return int((Decimal(total) / Decimal(count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class CadetResult:
    number: int
    cadet: Cadet
    averages: dict[str, int] | None  # whole numbers 1-5; None = no data. The value is also the band.
    total: int | None  # 6-30
    flagged: bool


def group_results(group, subjects=None) -> list[CadetResult]:
    """Results across all saved score sets, or only those for `subjects` when given."""
    cadets = list(Cadet.objects.filter(group=group, is_active=True).order_by("position", "name"))
    # Every saved score set counts for every cadet who takes its subject; a missing row counts
    # as all 3s (e.g. the cadet was added after the save). A cadet shows "no data" only when
    # no saved set covers a subject they take. A row for a subject the cadet was taken off is
    # kept in the database but ignored here.
    active_ids = {cadet.id for cadet in cadets}
    excluded = excluded_pairs(group)
    score_sets = ScoreSet.objects.filter(group=group)
    if subjects is not None:
        score_sets = score_sets.filter(subject__in=subjects)
    # One query: each set joined to its rows; a set with no rows comes back once with a
    # null cadet, so it still counts.
    set_subject = {}  # set id -> subject id
    rows = defaultdict(list)  # cadet id -> [values]
    for set_id, subject_id, cadet_id, *values in score_sets.values_list(
        "pk", "subject_id", "rows__cadet_id", *(f"rows__{f}" for f in ATTRIBUTE_FIELDS)
    ):
        set_subject[set_id] = subject_id
        if cadet_id in active_ids and (cadet_id, subject_id) not in excluded:
            rows[cadet_id].append(values)
    set_subjects = list(set_subject.values())

    results = []
    for number, cadet in enumerate(cadets, start=1):
        set_count = sum(1 for s in set_subjects if (cadet.id, s) not in excluded)
        if set_count == 0:
            results.append(CadetResult(number, cadet, None, None, False))
            continue
        cadet_rows = rows.get(cadet.id, [])
        missing = set_count - len(cadet_rows)
        averages = {
            field: round_average(
                sum(BLANK_COUNTS_AS if row[i] is None else row[i] for row in cadet_rows)
                + BLANK_COUNTS_AS * missing,
                set_count,
            )
            for i, field in enumerate(ATTRIBUTE_FIELDS)
        }
        results.append(
            CadetResult(
                number,
                cadet,
                averages,
                sum(averages.values()),
                any(v < FLAG_BELOW for v in averages.values()),
            )
        )
    return results
