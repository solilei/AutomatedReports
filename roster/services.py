import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

from django.db import transaction
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


@dataclass
class GroupChange:
    number: str
    is_new: bool
    course_old: str | None
    course_new: str
    added: list[str] = field(default_factory=list)
    deactivated: list[str] = field(default_factory=list)
    reactivated: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    unchanged: int = 0


def _diff_group(upload, number, entries, group):
    """Compare one group's file entries with the database; returns the change and actions.

    The actions list holds (kind, cadet_or_None, entry, position) in file order.
    """
    id_mode = upload.parsed["id_mode"]
    change = GroupChange(
        number=number,
        is_new=group is None,
        course_old=group.course_number if group else None,
        course_new=upload.course_number,
    )
    existing = {}
    if group is not None:
        for cadet in group.cadets.all():
            existing[cadet.external_id if id_mode else cadet.name] = cadet
    steps = []
    in_file = set()
    for position, entry in enumerate(entries, start=1):
        key = entry["external_id"] if id_mode else entry["name"]
        in_file.add(key)
        cadet = existing.get(key)
        if cadet is None:
            change.added.append(entry["name"])
            steps.append(("add", None, entry, position))
            continue
        if not cadet.is_active:
            change.reactivated.append(entry["name"])
            steps.append(("reactivate", cadet, entry, position))
        elif id_mode and cadet.name != entry["name"]:
            change.renamed.append((cadet.name, entry["name"]))
            steps.append(("rename", cadet, entry, position))
        else:
            change.unchanged += 1
            steps.append(("keep", cadet, entry, position))
    for key, cadet in existing.items():
        if key not in in_file and cadet.is_active:
            change.deactivated.append(cadet.name)
            steps.append(("deactivate", cadet, None, cadet.position))
    return change, steps


def _diff_upload(upload):
    from .models import Group

    numbers = sorted(upload.parsed["groups"])
    groups = {g.number: g for g in Group.objects.filter(number__in=numbers)}
    return [
        _diff_group(upload, number, upload.parsed["groups"][number], groups.get(number))
        for number in numbers
    ]


def build_preview(upload):
    return [change for change, _ in _diff_upload(upload)]


def apply_upload(upload, actor, actor_label=None):
    """Apply a parsed upload to the roster. The caller checks `check_groups` first."""
    from audit import actions
    from audit.service import log

    from .models import Cadet, Group

    id_mode = upload.parsed["id_mode"]
    applied = []
    with transaction.atomic():
        for change, steps in _diff_upload(upload):
            number = change.number

            def event(action, summary, **details):
                log(
                    actor,
                    action,
                    summary,
                    group_number=number,
                    details=details,
                    actor_label=actor_label,
                )

            if change.is_new:
                group = Group.objects.create(
                    number=number,
                    course_number=upload.course_number,
                    identity_mode="id" if id_mode else "name",
                )
                event(
                    actions.GROUP_CREATED,
                    f"Group {number} created (course {upload.course_number})",
                    course_number=upload.course_number,
                )
            else:
                group = Group.objects.get(number=number)
                if group.course_number != upload.course_number:
                    old = group.course_number
                    group.course_number = upload.course_number
                    group.save(update_fields=["course_number"])
                    event(
                        actions.GROUP_COURSE_CHANGED,
                        f"Group {number} course changed from {old} to {upload.course_number}",
                        old=old,
                        new=upload.course_number,
                    )
            for kind, cadet, entry, position in steps:
                if kind == "add":
                    cadet = Cadet.objects.create(
                        group=group,
                        name=entry["name"],
                        external_id=entry["external_id"],
                        position=position,
                    )
                    action, summary = actions.CADET_ADDED, f"Cadet {cadet.name} added"
                    extra = {}
                elif kind == "deactivate":
                    cadet.is_active = False
                    cadet.save(update_fields=["is_active"])
                    action, summary = actions.CADET_DEACTIVATED, f"Cadet {cadet.name} deactivated"
                    extra = {}
                else:
                    old_name = cadet.name
                    cadet.position = position
                    cadet.name = entry["name"]
                    cadet.is_active = True
                    cadet.save(update_fields=["position", "name", "is_active"])
                    if kind == "keep":
                        continue
                    if kind == "reactivate":
                        action = actions.CADET_REACTIVATED
                        summary = f"Cadet {cadet.name} reactivated"
                        extra = {}
                    else:
                        action = actions.CADET_RENAMED
                        summary = f"Cadet {old_name} renamed to {cadet.name}"
                        extra = {"old": old_name, "new": cadet.name}
                event(
                    action,
                    f"{summary} in {number}",
                    cadet=cadet.name,
                    external_id=cadet.external_id,
                    **extra,
                )
            applied.append(number)
        upload.status = "applied"
        upload.file_content = b""
        upload.parsed = {}
        upload.save()
        log(
            actor,
            actions.ROSTER_APPLIED,
            f"Applied roster '{upload.original_filename}' to groups {', '.join(applied)}",
            details={"upload_id": upload.pk, "groups": applied},
            actor_label=actor_label,
        )
    return applied
