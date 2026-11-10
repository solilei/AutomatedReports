import difflib
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from io import BytesIO

from django.db import transaction
from django.utils import timezone
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


HEADER_SEARCH_ROWS = 10  # title rows allowed above the header row


@dataclass
class Sheet:
    headers: list[str]
    rows: list[list[str]]
    header_row: int  # 1-based spreadsheet row number of the headers

    @property
    def first_data_row(self):
        return self.header_row + 1


def _is_header(cells):
    return sum(1 for v in cells if cell_text(v)) >= 2


def read_roster(content):
    """Read the first sheet. The header row is the first row with two or more filled
    cells; rows above it with at most one filled cell (titles, blank rows) are skipped."""
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            rows = workbook.worksheets[0].iter_rows(values_only=True)
            first, header_row = (), 1
            for number, row in enumerate(rows, start=1):
                if _is_header(row):
                    first, header_row = row, number
                    break
                if number >= HEADER_SEARCH_ROWS:
                    break
            headers = [cell_text(v) for v in first]
            width = len(headers)
            data = []
            if width:
                for row in rows:
                    cells = [cell_text(v) for v in row[:width]]
                    data.append(cells + [""] * (width - len(cells)))
        finally:
            workbook.close()
    except Exception as exc:
        raise RosterError(str(exc)) from exc
    return Sheet(headers, data, header_row)


def read_sheet(content):
    sheet = read_roster(content)
    return sheet.headers, sheet.rows


GROUP_NUMBER_RE = re.compile(r"(?=.*[A-Za-z0-9])[A-Za-z0-9._-]{1,20}")
NAME_MAX_LENGTH = 200  # Cadet.name
ID_MAX_LENGTH = 50  # Cadet.external_id
DIGITS_RE = re.compile(r"[0-9]+")


def normalise_id(value):
    """Digit-only IDs ignore leading zeros, so '00123' typed as text matches the number 123."""
    if DIGITS_RE.fullmatch(value):
        return value.lstrip("0") or "0"
    return value


@dataclass
class ParseResult:
    groups: dict[str, list[dict]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def name_key(name):
    """Without an ID column, names identify cadets ignoring case: 'JOHN SMITH' is 'John Smith'."""
    return name.casefold()


def parse_rows(rows, group_number, name_col, id_col=None, first_row=2):
    result = ParseResult()
    seen = {}
    for index, row in enumerate(rows):
        number = first_row + index
        name = " ".join(row[name_col].split())
        external_id = normalise_id(row[id_col].strip()) if id_col is not None else ""
        if not (name or external_id):
            continue
        problems = []
        if not name:
            problems.append(f"Row {number}: name is blank.")
        elif len(name) > NAME_MAX_LENGTH:
            problems.append(f"Row {number}: name is longer than {NAME_MAX_LENGTH} characters.")
        if id_col is not None and not external_id:
            problems.append(f"Row {number}: cadet ID is blank.")
        elif len(external_id) > ID_MAX_LENGTH:
            problems.append(f"Row {number}: cadet ID is longer than {ID_MAX_LENGTH} characters.")
        if problems:
            result.errors.extend(problems)
            continue
        result.groups.setdefault(group_number, []).append(
            {"name": name, "external_id": external_id, "row": number}
        )
        key = (group_number, external_id if id_col is not None else name_key(name))
        _, numbers = seen.setdefault(key, (external_id or name, []))
        numbers.append(number)
    for (group, _key), (value, numbers) in seen.items():
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
    added: list[str] = field(default_factory=list)
    deactivated: list[str] = field(default_factory=list)
    reactivated: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    unchanged: int = 0
    # Name mode only: (no longer present, added) pairs that look like one cadet respelled.
    possible_respellings: list[tuple[str, str]] = field(default_factory=list)


RESPELLING_CUTOFF = 0.8  # difflib similarity ratio


def _possible_respellings(removed, added):
    pairs = []
    candidates = list(added)
    for old in removed:
        match = difflib.get_close_matches(old, candidates, n=1, cutoff=RESPELLING_CUTOFF)
        if match:
            pairs.append((old, match[0]))
            candidates.remove(match[0])
    return pairs


def _diff_group(upload, number, entries, group):
    """Compare one group's file entries with the database; returns the change and actions.

    The actions list holds (kind, cadet_or_None, entry, position) in file order.
    """
    id_mode = upload.parsed["id_mode"]
    change = GroupChange(
        number=number,
        is_new=group is None,
    )
    existing = {}
    if group is not None:
        for cadet in group.cadets.all():
            existing[normalise_id(cadet.external_id) if id_mode else name_key(cadet.name)] = cadet
    steps = []
    in_file = set()
    for position, entry in enumerate(entries, start=1):
        key = entry["external_id"] if id_mode else name_key(entry["name"])
        in_file.add(key)
        cadet = existing.get(key)
        if cadet is None:
            change.added.append(entry["name"])
            steps.append(("add", None, entry, position))
            continue
        if not cadet.is_active:
            change.reactivated.append(entry["name"])
            steps.append(("reactivate", cadet, entry, position))
        elif cadet.name != entry["name"]:
            # ID mode: any new name. Name mode: same name, different capitals.
            change.renamed.append((cadet.name, entry["name"]))
            steps.append(("rename", cadet, entry, position))
        else:
            change.unchanged += 1
            steps.append(("keep", cadet, entry, position))
    for key, cadet in existing.items():
        if key not in in_file and cadet.is_active:
            change.deactivated.append(cadet.name)
            steps.append(("deactivate", cadet, None, cadet.position))
    if not id_mode:
        change.possible_respellings = _possible_respellings(change.deactivated, change.added)
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


def preview_key(changes):
    """Fingerprint of a preview; it differs whenever confirming would apply different changes."""
    payload = json.dumps([asdict(change) for change in changes], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def apply_upload(upload, actor, actor_label=None):
    """Apply a parsed upload to the roster. The caller checks `check_groups` first."""
    from audit import actions
    from audit.service import log

    from .models import Cadet, Group

    id_mode = upload.parsed["id_mode"]
    applied = []
    with transaction.atomic():
        # Hold the existing groups so a score save or another upload waits for this one.
        list(Group.objects.select_for_update().filter(number__in=list(upload.parsed["groups"])))
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
                    programme=upload.programme,
                    number=number,
                    identity_mode="id" if id_mode else "name",
                )
                event(
                    actions.GROUP_CREATED,
                    f"Group {number} created",
                    programme=upload.programme.name,
                )
            else:
                group = Group.objects.get(number=number)
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
                    cadet.external_id = entry["external_id"]
                    cadet.is_active = True
                    cadet.save(update_fields=["position", "name", "external_id", "is_active"])
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


OPEN_UPLOAD_STATUSES = ["uploaded", "parsed"]
STALE_UPLOAD_AGE = timedelta(hours=24)


def discard_upload(upload, actor, *, actor_label=None, reason=""):
    """Delete an open upload's stored file and parsed rows, and log it."""
    from audit import actions
    from audit.service import log

    upload.status = "discarded"
    upload.file_content = b""
    upload.parsed = {}
    upload.save()
    summary = f"Roster '{upload.original_filename}' discarded"
    details = {"upload_id": upload.pk, "filename": upload.original_filename}
    if reason:
        summary += f" ({reason})"
        details["reason"] = reason
    log(actor, actions.ROSTER_DISCARDED, summary, details=details, actor_label=actor_label)


def discard_stale_uploads(max_age=STALE_UPLOAD_AGE):
    """Discard uploads left unfinished for longer than max_age; return how many."""
    from .models import RosterUpload

    cutoff = timezone.now() - max_age
    count = 0
    with transaction.atomic():
        stale = RosterUpload.objects.select_for_update().filter(
            status__in=OPEN_UPLOAD_STATUSES, uploaded_at__lt=cutoff
        )
        for upload in stale:
            discard_upload(
                upload, None, actor_label="system", reason="left unfinished for over 24 hours"
            )
            count += 1
    return count
