from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import admin_required
from audit import actions
from audit.service import log

from .forms import ColumnForm, UploadForm
from .models import RosterColumnPreference, RosterUpload
from .services import apply_upload, build_preview, check_groups, parse_rows, read_sheet


def home(request):
    return render(request, "roster/home.html")


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
