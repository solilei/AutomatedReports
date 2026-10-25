import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook


class RosterError(Exception):
    pass


def cell_text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return " ".join(str(v).split())


def read_sheet(content):
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            rows = workbook.worksheets[0].iter_rows(values_only=True)
            first = next(rows, ())
            headers = [cell_text(v) for v in first]
            width = len(headers)
            data = []
            for row in rows:
                cells = [cell_text(v) for v in row[:width]]
                data.append(cells + [""] * (width - len(cells)))
        finally:
            workbook.close()
    except Exception as exc:
        raise RosterError(str(exc)) from exc
    return headers, data


GROUP_NUMBER_RE = re.compile(r"[A-Za-z0-9._-]{1,20}")


@dataclass
class ParseResult:
    groups: dict[str, list[dict]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def parse_rows(rows, group_col, name_col, id_col=None):
    result = ParseResult()
    seen = {}
    for index, row in enumerate(rows):
        number = index + 2
        group = row[group_col].strip().upper()
        name = " ".join(row[name_col].split())
        external_id = row[id_col].strip() if id_col is not None else ""
        if not (group or name or external_id):
            continue
        problems = []
        if not group:
            problems.append(f"Row {number}: group is blank.")
        elif not GROUP_NUMBER_RE.fullmatch(group):
            problems.append(
                f"Row {number}: group number '{group}' may only contain letters, digits, "
                "'.', '_' and '-' (max 20 characters)."
            )
        if not name:
            problems.append(f"Row {number}: name is blank.")
        if id_col is not None and not external_id:
            problems.append(f"Row {number}: cadet ID is blank.")
        if problems:
            result.errors.extend(problems)
            continue
        result.groups.setdefault(group, []).append(
            {"name": name, "external_id": external_id, "row": number}
        )
        key = (group, external_id if id_col is not None else name)
        seen.setdefault(key, []).append(number)
    for (group, value), numbers in seen.items():
        if len(numbers) < 2:
            continue
        listed = ", ".join(str(n) for n in numbers)
        if id_col is not None:
            result.errors.append(
                f"Cadet ID '{value}' appears more than once in group {group} (rows {listed})."
            )
        else:
            result.errors.append(
                f"Group {group} has more than one cadet named '{value}' (rows {listed}). "
                "Fix the file and upload it again."
            )
    if not result.groups and not result.errors:
        result.errors.append("The file contains no cadets.")
    return result


def check_groups(group_numbers, id_mode):
    from .models import DeletedGroupNumber, Group

    existing = {g.number: g for g in Group.objects.filter(number__in=group_numbers)}
    deleted = set(
        DeletedGroupNumber.objects.filter(number__in=group_numbers).values_list(
            "number", flat=True
        )
    )
    errors = []
    for number in group_numbers:
        group = existing.get(number)
        if group is not None:
            if group.status == Group.Status.LOCKED:
                errors.append(f"Group {number} is locked; unlock it before uploading.")
            elif group.status == Group.Status.ARCHIVED:
                errors.append(f"Group {number} is archived and its number cannot be reused.")
            elif group.identity_mode == "id" and not id_mode:
                errors.append(
                    f"Group {number} was first uploaded with a Cadet ID column; "
                    "choose a Cadet ID column."
                )
            elif group.identity_mode == "name" and id_mode:
                errors.append(
                    f"Group {number} was first uploaded without a Cadet ID column; "
                    "set Cadet ID to — none —."
                )
        elif number in deleted:
            errors.append(f"Group {number} was deleted and its number cannot be reused.")
    return errors
