from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from roster.models import Cadet
from scoring.attributes import ATTRIBUTE_FIELDS, BLANK_COUNTS_AS
from scoring.models import CadetScore

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


def group_results(group) -> list[CadetResult]:
    cadets = list(Cadet.objects.filter(group=group, is_active=True).order_by("position", "name"))
    rows = defaultdict(list)
    for cadet_id, *values in CadetScore.objects.filter(
        score_set__group=group, cadet__in=cadets
    ).values_list("cadet_id", *ATTRIBUTE_FIELDS):
        rows[cadet_id].append(values)

    results = []
    for number, cadet in enumerate(cadets, start=1):
        cadet_rows = rows.get(cadet.id)
        if not cadet_rows:
            results.append(CadetResult(number, cadet, None, None, False))
            continue
        averages = {
            field: round_average(
                sum(BLANK_COUNTS_AS if row[i] is None else row[i] for row in cadet_rows),
                len(cadet_rows),
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
