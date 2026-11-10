from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from audit import actions
from audit.service import log

from scoring.access import get_visible_group, scored_subjects
from scoring.models import ScoreSet, Subject

from . import lifecycle
from .forms import ColumnForm, UploadForm
from .models import Cadet, Group, RosterColumnPreference, RosterUpload
from .services import (
    apply_upload,
    build_preview,
    check_groups,
    discard_stale_uploads,
    discard_upload,
    parse_rows,
    preview_key,
    read_roster,
)


def home(request):
    groups = Group.objects.filter(status__in=[Group.Status.ACTIVE, Group.Status.LOCKED])
    return render(request, "roster/home.html", {"groups": groups})


def group_go(request):
    number = request.GET.get("number", "").strip().upper()
    if not Group.objects.filter(number=number).exists():
        messages.error(request, "Group not found.")
        return redirect("home")
    return redirect("roster:group_detail", number=number)


def group_detail(request, number):
    group = get_visible_group(request, number)
    return render(
        request,
        "roster/group_detail.html",
        {
            "group": group,
            "active_count": group.cadets.filter(is_active=True).count(),
            "subjects": Subject.objects.filter(is_active=True),
            "score_sets": ScoreSet.objects.filter(instructor=request.user, group=group)
            .select_related("subject")
            .order_by("subject__name"),
            # Colleagues' score sets for subjects this user has also scored in this group.
            "shared_score_sets": ScoreSet.objects.filter(
                group=group, subject__in=scored_subjects(request.user, group)
            )
            .exclude(instructor=request.user)
            .select_related("subject", "instructor")
            .order_by("subject__name", "instructor__username"),
        },
    )


@admin_required
def group_list(request):
    groups = Group.objects.annotate(
        active_count=Count("cadets", filter=Q(cadets__is_active=True), distinct=True),
        inactive_count=Count("cadets", filter=Q(cadets__is_active=False), distinct=True),
        score_set_count=Count("score_sets", distinct=True),
    )
    return render(request, "roster/group_list.html", {"groups": groups})


def _lifecycle_action(request, number, action):
    group = get_object_or_404(Group, number=number)
    error = lifecycle.change_status(group, action, request.user)
    if error:
        messages.error(request, error)
    return redirect("roster:group_detail", number=group.number)


@admin_required
@require_POST
def group_lock(request, number):
    return _lifecycle_action(request, number, "lock")


@admin_required
@require_POST
def group_unlock(request, number):
    return _lifecycle_action(request, number, "unlock")


@admin_required
@require_POST
def group_archive(request, number):
    return _lifecycle_action(request, number, "archive")


@admin_required
@require_POST
def group_unarchive(request, number):
    return _lifecycle_action(request, number, "unarchive")


@admin_required
def group_delete(request, number):
    group = get_object_or_404(Group, number=number)
    if group.status != Group.Status.ARCHIVED:
        messages.error(request, lifecycle.refusal("delete", group))
        return redirect("roster:group_detail", number=group.number)
    error = None
    if request.method == "POST":
        if request.POST.get("confirm_number") != group.number:
            error = "Type the group number to confirm."
        else:
            error = lifecycle.delete_group(group, request.user)
            if error:
                messages.error(request, error)
                return redirect("roster:group_detail", number=group.number)
            messages.success(request, f"Group {group.number} deleted.")
            return redirect("roster:group_list")
    return render(
        request,
        "roster/group_delete_confirm.html",
        {
            "group": group,
            "cadet_count": group.cadets.count(),
            "score_set_count": group.score_sets.count(),
            "error": error,
        },
    )


@admin_required
def cadet_list(request, number):
    group = get_object_or_404(Group, number=number)
    cadets = group.cadets.annotate(score_count=Count("scores"))
    return render(request, "roster/cadet_list.html", {"group": group, "cadets": cadets})


@admin_required
def cadet_delete(request, pk):
    cadet = get_object_or_404(Cadet.objects.select_related("group"), pk=pk)
    group = cadet.group
    if not group.is_editable:
        messages.error(request, f"Group is {group.status}; cadets cannot be deleted.")
        return redirect("roster:cadet_list", number=group.number)
    score_rows = cadet.scores.count()
    if request.method == "POST":
        with transaction.atomic():
            log(
                request.user,
                actions.CADET_DELETED,
                f"{request.user.username} deleted cadet {cadet.name} from group {group.number}",
                group_number=group.number,
                details={
                    "cadet": cadet.name,
                    "external_id": cadet.external_id,
                    "score_rows": score_rows,
                },
            )
            cadet.delete()
        messages.success(request, f"Cadet {cadet.name} deleted.")
        return redirect("roster:cadet_list", number=group.number)
    return render(
        request,
        "roster/cadet_delete_confirm.html",
        {"cadet": cadet, "group": group, "score_rows": score_rows},
    )


@admin_required
def upload(request):
    discard_stale_uploads()
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        record = RosterUpload.objects.create(
            uploaded_by=request.user,
            original_filename=form.cleaned_data["file"].name,
            file_content=form.content,
            group_number=form.cleaned_data["group_number"],
        )
        log(
            request.user,
            actions.ROSTER_UPLOADED,
            f"Roster '{record.original_filename}' uploaded",
            details={
                "filename": record.original_filename,
                "size_bytes": len(form.content),
                "upload_id": record.pk,
            },
        )
        return redirect("roster:upload_columns", pk=record.pk)
    return render(request, "roster/upload.html", {"form": form})


@admin_required
def upload_columns(request, pk):
    upload = get_object_or_404(RosterUpload, pk=pk)
    if closed := _closed_upload(request, upload):
        return closed
    sheet = read_roster(bytes(upload.file_content))
    headers, rows = sheet.headers, sheet.rows
    form = ColumnForm(headers, request.POST or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        name_col = int(form.cleaned_data["name_col"])
        id_col = int(form.cleaned_data["id_col"]) if form.cleaned_data["id_col"] else None
        result = parse_rows(rows, upload.group_number, name_col, id_col, sheet.first_data_row)
        errors = result.errors or check_groups(list(result.groups), id_col is not None)
        if not errors:
            upload.name_col, upload.id_col = name_col, id_col
            upload.parsed = {"id_mode": id_col is not None, "groups": result.groups}
            upload.status = "parsed"
            upload.save()
            pref = RosterColumnPreference.get()
            pref.name_header = headers[name_col]
            pref.id_header = headers[id_col] if id_col is not None else ""
            pref.save()
            return redirect("roster:upload_preview", pk=upload.pk)
    return render(
        request,
        "roster/upload_columns.html",
        {
            "form": form,
            "upload": upload,
            "headers": headers,
            "header_row": sheet.header_row,
            "sample_rows": rows[:5],
            "errors": errors,
        },
    )


def _closed_upload(request, upload):
    """Redirect away from an applied or discarded upload; None if it is still open."""
    if upload.status == "applied":
        messages.info(request, "This upload has already been applied.")
    elif upload.status == "discarded":
        messages.info(request, "This upload was discarded.")
    else:
        return None
    return redirect("roster:upload")


@admin_required
def upload_preview(request, pk):
    upload = get_object_or_404(RosterUpload, pk=pk)
    if upload.status == "uploaded":
        return redirect("roster:upload_columns", pk=upload.pk)
    if closed := _closed_upload(request, upload):
        return closed
    warning = ""
    if request.method == "POST":
        with transaction.atomic():
            upload = RosterUpload.objects.select_for_update().get(pk=pk)
            if closed := _closed_upload(request, upload):
                return closed
            numbers = list(upload.parsed["groups"])
            # Hold the groups so the preview checked below is what gets applied.
            list(Group.objects.select_for_update().filter(number__in=numbers))
            errors = check_groups(numbers, upload.parsed["id_mode"])
            changes = build_preview(upload)
            # A missing key (no browser form) skips the check; the page always sends one.
            seen_key = request.POST.get("preview_key")
            if seen_key and seen_key != preview_key(changes):
                warning = (
                    "The roster changed since this preview was shown. "
                    "Check the changes below and confirm again."
                )
            elif not errors:
                try:
                    apply_upload(upload, request.user)
                except IntegrityError:
                    # Another upload created the same new group at the same moment.
                    messages.error(
                        request,
                        "Another upload changed this group at the same time. "
                        "Check the changes and confirm again.",
                    )
                    return redirect("roster:upload_preview", pk=upload.pk)
                messages.success(request, "Roster applied.")
                return redirect("home")
    else:
        errors = check_groups(list(upload.parsed["groups"]), upload.parsed["id_mode"])
        changes = build_preview(upload)
    return render(
        request,
        "roster/upload_preview.html",
        {
            "upload": upload,
            "errors": errors,
            "warning": warning,
            "changes": changes,
            "preview_key": preview_key(changes),
        },
    )


@admin_required
@require_POST
def upload_discard(request, pk):
    with transaction.atomic():
        upload = get_object_or_404(RosterUpload.objects.select_for_update(), pk=pk)
        if closed := _closed_upload(request, upload):
            return closed
        discard_upload(upload, request.user)
    messages.success(request, "Upload discarded.")
    return redirect("roster:upload")
