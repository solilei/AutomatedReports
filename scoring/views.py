from io import BytesIO

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from audit import actions
from audit.service import log

from roster.models import Group

from .access import assigned_subjects, can_score, can_view_score_set, get_visible_group
from . import completeness, services
from .exclusions import cadets_taking
from .export import build_group_report
from .attributes import ATTRIBUTE_FIELDS, ATTRIBUTES, BLANK_COUNTS_AS, SCORE_CHOICES
from .forms import ProgrammeForm, SubjectForm
from .models import Programme, ScoreSet, Subject
from .results import BAND_HEX, group_results


FIXED_MESSAGE = "ATPL is fixed and cannot be changed."


def _refuse_fixed(request, programme):
    messages.error(request, FIXED_MESSAGE)
    return redirect("scoring:programme_detail", pk=programme.pk)


@admin_required
def subject_list(request):
    return redirect("scoring:programme_list")


@admin_required
def programme_list(request):
    programmes = Programme.objects.annotate(
        active_subjects=Count("subjects", filter=Q(subjects__is_active=True), distinct=True),
        group_count=Count("groups", distinct=True),
    )
    return render(request, "scoring/programme_list.html", {"programmes": programmes})


@admin_required
def programme_create(request):
    form = ProgrammeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        programme = form.save()
        log(
            request.user,
            actions.PROGRAMME_CREATED,
            f"Programme '{programme.name}' created",
            details={"name": programme.name, "group_prefix": programme.group_prefix},
        )
        messages.success(request, f"Programme '{programme.name}' created.")
        return redirect("scoring:programme_detail", pk=programme.pk)
    return render(request, "scoring/programme_form.html", {"form": form, "programme": None})


@admin_required
def programme_detail(request, pk):
    programme = get_object_or_404(Programme, pk=pk)
    subjects = programme.subjects.prefetch_related("instructors").order_by("name")
    rows = [
        {
            "subject": subject,
            "instructors": [
                user.display_name + ("" if user.is_active else " (deactivated)")
                for user in sorted(subject.instructors.all(), key=lambda u: u.display_name.lower())
            ],
        }
        for subject in subjects
    ]
    return render(request, "scoring/programme_detail.html", {"programme": programme, "rows": rows})


@admin_required
def programme_edit(request, pk):
    programme = get_object_or_404(Programme, pk=pk)
    if programme.is_fixed:
        return _refuse_fixed(request, programme)
    old_name = programme.name
    form = ProgrammeForm(request.POST or None, instance=programme)
    if request.method == "POST" and form.is_valid():
        programme = form.save()
        if programme.name != old_name:
            log(
                request.user,
                actions.PROGRAMME_RENAMED,
                f"Programme '{old_name}' renamed to '{programme.name}'",
                details={"old": old_name, "new": programme.name},
            )
        messages.success(request, "Programme saved.")
        return redirect("scoring:programme_detail", pk=programme.pk)
    return render(request, "scoring/programme_form.html", {"form": form, "programme": programme})


@admin_required
@require_POST
def programme_toggle(request, pk):
    programme = get_object_or_404(Programme, pk=pk)
    if programme.is_fixed:
        return _refuse_fixed(request, programme)
    programme.is_active = not programme.is_active
    programme.save(update_fields=["is_active"])
    if programme.is_active:
        action, verb = actions.PROGRAMME_REACTIVATED, "reactivated"
    else:
        action, verb = actions.PROGRAMME_DEACTIVATED, "deactivated"
    log(request.user, action, f"Programme '{programme.name}' {verb}", details={"name": programme.name})
    messages.success(request, f"Programme '{programme.name}' {verb}.")
    return redirect("scoring:programme_detail", pk=programme.pk)


@admin_required
def subject_create(request, programme_pk):
    programme = get_object_or_404(Programme, pk=programme_pk)
    if programme.is_fixed:
        return _refuse_fixed(request, programme)
    form = SubjectForm(request.POST or None, programme=programme)
    if request.method == "POST" and form.is_valid():
        subject = form.save(commit=False)
        subject.programme = programme
        subject.save()
        log(
            request.user,
            actions.SUBJECT_CREATED,
            f"Subject '{subject.name}' created in programme '{programme.name}'",
            details={"name": subject.name, "programme": programme.name},
        )
        messages.success(request, f"Subject '{subject.name}' created.")
        return redirect("scoring:programme_detail", pk=programme.pk)
    return render(
        request, "scoring/subject_form.html", {"form": form, "subject": None, "programme": programme}
    )


@admin_required
def subject_edit(request, pk):
    subject = get_object_or_404(Subject.objects.select_related("programme"), pk=pk)
    if subject.is_fixed:
        return _refuse_fixed(request, subject.programme)
    old_name = subject.name
    form = SubjectForm(request.POST or None, instance=subject)
    if request.method == "POST" and form.is_valid():
        subject = form.save()
        if subject.name != old_name:
            log(
                request.user,
                actions.SUBJECT_RENAMED,
                f"Subject '{old_name}' renamed to '{subject.name}'",
                details={"old": old_name, "new": subject.name},
            )
            messages.success(request, f"Subject renamed to '{subject.name}'.")
        return redirect("scoring:programme_detail", pk=subject.programme_id)
    return render(
        request,
        "scoring/subject_form.html",
        {"form": form, "subject": subject, "programme": subject.programme},
    )


@admin_required
@require_POST
def subject_toggle(request, pk):
    subject = get_object_or_404(Subject.objects.select_related("programme"), pk=pk)
    if subject.is_fixed:
        return _refuse_fixed(request, subject.programme)
    subject.is_active = not subject.is_active
    subject.save(update_fields=["is_active"])
    if subject.is_active:
        action, verb = actions.SUBJECT_REACTIVATED, "reactivated"
    else:
        action, verb = actions.SUBJECT_DEACTIVATED, "deactivated"
    log(request.user, action, f"Subject '{subject.name}' {verb}", details={"name": subject.name})
    messages.success(request, f"Subject '{subject.name}' {verb}.")
    return redirect("scoring:programme_detail", pk=subject.programme_id)


def score_go(request, number):
    group = get_visible_group(request, number)
    try:
        subject_id = int(request.GET.get("subject", ""))
    except ValueError:
        return redirect("roster:group_detail", number=group.number)
    subject = Subject.objects.filter(pk=subject_id, is_active=True).first()
    if subject is None:
        return redirect("roster:group_detail", number=group.number)
    if not can_score(request.user, group, subject):
        raise PermissionDenied
    return redirect("scoring:score_grid", number=group.number, subject_id=subject_id)


def _build_rows(group, subject, score_set, submitted=None):
    saved = {row.cadet_id: row for row in score_set.rows.all()} if score_set else {}
    rows = []
    for number_, cadet in enumerate(cadets_taking(group, subject), start=1):
        saved_row = saved.get(cadet.pk)
        entry = submitted.get(cadet.pk) if submitted else None
        if entry:
            values, comment = entry["scores"], entry["raw_comment"]
        else:
            values = {f: getattr(saved_row, f) if saved_row else None for f, _l, _h in ATTRIBUTES}
            comment = saved_row.comment if saved_row else ""
        rows.append(
            {
                "number": number_,
                "cadet": cadet,
                "added": score_set is not None and saved_row is None,
                "cells": [
                    {
                        "field": field,
                        "name": f"s-{cadet.pk}-{field}",
                        "value": values[field],
                        "filled": field in (entry["filled"] if entry else ()),
                    }
                    for field, _label, _header in ATTRIBUTES
                ],
                "comment": comment,
            }
        )
    return rows


def _render_grid(request, group, subject, score_set, submitted=None, errors=(), warning="", fill_notice=False):
    rows = _build_rows(group, subject, score_set, submitted)
    return render(
        request,
        "scoring/score_grid.html",
        {
            "group": group,
            "subject": subject,
            "score_set": score_set,
            "rows": rows,
            "cadet_ids": ",".join(str(row["cadet"].pk) for row in rows),
            "attributes": ATTRIBUTES,
            "score_choices": SCORE_CHOICES,
            "editable": group.is_editable,
            "errors": errors,
            "warning": warning,
            "fill_notice": fill_notice,
        },
    )


def score_grid(request, number, subject_id):
    group = get_visible_group(request, number)
    subject = get_object_or_404(Subject, pk=subject_id)
    if not can_score(request.user, group, subject):
        raise PermissionDenied
    score_set = ScoreSet.objects.filter(
        instructor=request.user, subject=subject, group=group
    ).first()
    if score_set is None and not subject.is_active:
        messages.error(request, f"Subject '{subject.name}' is no longer in use.")
        return redirect("roster:group_detail", number=group.number)
    if request.method != "POST":
        return _render_grid(request, group, subject, score_set)
    if not group.is_editable:
        raise PermissionDenied
    cadets = list(cadets_taking(group, subject))
    data, errors = services.parse_submission(request.POST, cadets)
    for cadet in cadets:
        data[cadet.pk]["raw_comment"] = request.POST.get(f"c-{cadet.pk}", "")
    # A missing list (no browser form) skips the check; the page always sends one.
    shown = request.POST.get("cadet_ids")
    if shown is not None and _id_set(shown) != {cadet.pk for cadet in cadets}:
        return _render_grid(request, group, subject, score_set, data, warning=ROSTER_CHANGED)
    if errors:
        return _render_grid(request, group, subject, score_set, data, errors)
    blank_cells, blank_cadets, scored_cells = services.count_blanks(data)
    if scored_cells == 0:
        return _render_grid(
            request, group, subject, score_set, data, ["Enter at least one score before saving."]
        )
    if blank_cells:
        # Nothing is saved with a blank cell. Fill the blanks with 3 and ask the user to confirm.
        for entry in data.values():
            entry["filled"] = [f for f, v in entry["scores"].items() if v is None]
            for field in entry["filled"]:
                entry["scores"][field] = BLANK_COUNTS_AS
        warning = (
            f"{blank_cells} blank cell(s) were filled with {BLANK_COUNTS_AS}. "
            "Check them, then click Confirm and save."
        )
        return _render_grid(
            request, group, subject, score_set, data, warning=warning, fill_notice=True
        )
    with transaction.atomic():
        # Hold the group row so a lock or roster upload can't land mid-save, then re-check both.
        locked_group = Group.objects.select_for_update().get(pk=group.pk)
        current = set(cadets_taking(locked_group, subject).values_list("pk", flat=True))
        if locked_group.is_editable and current == set(data):
            services.save_score_set(request.user, subject, locked_group, data)
            saved = True
        else:
            saved = False
    if saved:
        messages.success(request, "Saved.")
    elif not locked_group.is_editable:
        messages.error(request, f"Not saved: group {group.number} is now {locked_group.status}.")
    else:
        messages.error(request, f"Not saved: {ROSTER_CHANGED}")
    return redirect("scoring:score_grid", number=group.number, subject_id=subject.pk)


ROSTER_CHANGED = (
    "The cadet list changed since you opened this page. "
    "Check the list below and save again."
)


def _id_set(text):
    try:
        return {int(part) for part in text.split(",") if part}
    except ValueError:
        return None


@admin_required
def missing_scores(request):
    return render(request, "scoring/missing_scores.html", {"gaps": completeness.missing_scores()})


def my_score_sets(request):
    score_sets = ScoreSet.objects.filter(
        instructor=request.user, subject__instructors=request.user
    ).select_related("group", "subject")
    if not request.user.is_admin:
        score_sets = score_sets.exclude(group__status=Group.Status.ARCHIVED)
    return render(
        request, "scoring/my_score_sets.html", {"score_sets": score_sets.order_by("-updated_at")}
    )


@admin_required
def group_score_sets(request, number):
    group = get_object_or_404(Group, number=number)
    score_sets = group.score_sets.select_related("instructor", "subject").order_by("-updated_at")
    return render(
        request, "scoring/group_score_sets.html", {"group": group, "score_sets": score_sets}
    )


def score_set_detail(request, pk):
    score_set = get_object_or_404(
        ScoreSet.objects.select_related("group", "subject", "instructor"), pk=pk
    )
    if not can_view_score_set(request.user, score_set):
        raise PermissionDenied
    rows = score_set.rows.select_related("cadet").order_by(
        "-cadet__is_active", "cadet__position", "cadet__pk"
    )
    table = [
        {
            "number": number_,
            "cadet": row.cadet,
            "values": [getattr(row, field) for field, _label, _header in ATTRIBUTES],
            "comment": row.comment,
        }
        for number_, row in enumerate(rows, start=1)
    ]
    return render(
        request,
        "scoring/score_set_detail.html",
        {"score_set": score_set, "attributes": ATTRIBUTES, "rows": table},
    )


def results(request, number):
    group = get_visible_group(request, number)
    if request.user.is_admin:
        choices = list(Subject.objects.filter(scoreset__group=group).distinct())
        subjects = None  # every subject
    else:
        # Instructors see combined results only for the subjects assigned to them.
        choices = assigned_subjects(request.user, group.programme)
        subjects = choices
    # Optional ?subject=<id> narrows the results to one of the allowed subjects.
    selected = next((s for s in choices if str(s.pk) == request.GET.get("subject")), None)
    if selected is not None:
        subjects = [selected]
    score_sets = group.score_sets.all()
    if subjects is not None:
        score_sets = score_sets.filter(subject__in=subjects)
    return render(
        request,
        "scoring/results.html",
        {
            "group": group,
            "rows": [
                (result, [result.averages[field] for field in ATTRIBUTE_FIELDS] if result.averages else None)
                for result in group_results(group, subjects)
            ],
            "subjects": subjects,
            "subject_choices": choices,
            "selected_subject": selected,
            "attributes": ATTRIBUTES,
            "score_set_count": score_sets.count(),
            "no_saved_sets": subjects is not None and not group.score_sets.filter(subject__in=subjects).exists(),
            "key": [(value, BAND_HEX[value], label) for value, label in SCORE_CHOICES],
        },
    )


@admin_required
def export(request, number):
    group = get_object_or_404(Group, number=number)
    export_date = timezone.localdate()
    buffer = BytesIO()
    build_group_report(group, export_date).save(buffer)
    filename = f"Cadet_Soft_Skills_{group.number}_{export_date:%Y-%m-%d}.xlsx"
    log(
        request.user,
        actions.EXPORT_DOWNLOADED,
        f"{request.user.username} exported the report for group {group.number}",
        group_number=group.number,
        details={"filename": filename},
    )
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
