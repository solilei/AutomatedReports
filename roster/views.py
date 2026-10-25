from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from audit import actions
from audit.service import log

from scoring.access import get_visible_group
from scoring.models import ScoreSet, Subject

from . import lifecycle
from .forms import ColumnForm, UploadForm
from .models import Cadet, Group, RosterColumnPreference, RosterUpload
from .services import apply_upload, build_preview, check_groups, parse_rows, read_sheet


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
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        record = RosterUpload.objects.create(
            uploaded_by=request.user,
            original_filename=form.cleaned_data["file"].name,
            file_content=form.content,
            course_number=form.cleaned_data["course_number"],
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
    if upload.status == "applied":
        messages.info(request, "This upload has already been applied.")
        return redirect("roster:upload")
    headers, rows = read_sheet(bytes(upload.file_content))
    form = ColumnForm(headers, request.POST or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        group_col = int(form.cleaned_data["group_col"])
        name_col = int(form.cleaned_data["name_col"])
        id_col = int(form.cleaned_data["id_col"]) if form.cleaned_data["id_col"] else None
        result = parse_rows(rows, group_col, name_col, id_col)
        errors = result.errors or check_groups(list(result.groups), id_col is not None)
        if not errors:
            upload.group_col, upload.name_col, upload.id_col = group_col, name_col, id_col
            upload.parsed = {"id_mode": id_col is not None, "groups": result.groups}
            upload.status = "parsed"
            upload.save()
            pref = RosterColumnPreference.get()
            pref.group_header = headers[group_col]
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
            "sample_rows": rows[:5],
            "errors": errors,
        },
    )


@admin_required
def upload_preview(request, pk):
    upload = get_object_or_404(RosterUpload, pk=pk)
    if upload.status == "uploaded":
        return redirect("roster:upload_columns", pk=upload.pk)
    if upload.status == "applied":
        messages.info(request, "This upload has already been applied.")
        return redirect("roster:upload")
    if request.method == "POST":
        with transaction.atomic():
            upload = RosterUpload.objects.select_for_update().get(pk=pk)
            if upload.status != "parsed":
                messages.info(request, "This upload has already been applied.")
                return redirect("roster:upload")
            errors = check_groups(list(upload.parsed["groups"]), upload.parsed["id_mode"])
            if not errors:
                apply_upload(upload, request.user)
                messages.success(request, "Roster applied.")
                return redirect("home")
    else:
        errors = check_groups(list(upload.parsed["groups"]), upload.parsed["id_mode"])
    return render(
        request,
        "roster/upload_preview.html",
        {"upload": upload, "errors": errors, "changes": build_preview(upload)},
    )
