from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from audit import actions
from audit.service import log

from .access import get_visible_group
from .attributes import ATTRIBUTES, SCORE_CHOICES
from .forms import SubjectForm
from .models import ScoreSet, Subject


@admin_required
def subject_list(request):
    return render(request, "scoring/subject_list.html", {"subjects": Subject.objects.all()})


@admin_required
def subject_create(request):
    form = SubjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        subject = form.save()
        log(request.user, actions.SUBJECT_CREATED, f"Subject '{subject.name}' created", details={"name": subject.name})
        messages.success(request, f"Subject '{subject.name}' created.")
        return redirect("scoring:subject_list")
    return render(request, "scoring/subject_form.html", {"form": form, "subject": None})


@admin_required
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
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
        return redirect("scoring:subject_list")
    return render(request, "scoring/subject_form.html", {"form": form, "subject": subject})


@admin_required
@require_POST
def subject_toggle(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    subject.is_active = not subject.is_active
    subject.save(update_fields=["is_active"])
    if subject.is_active:
        action, verb = actions.SUBJECT_REACTIVATED, "reactivated"
    else:
        action, verb = actions.SUBJECT_DEACTIVATED, "deactivated"
    log(request.user, action, f"Subject '{subject.name}' {verb}", details={"name": subject.name})
    messages.success(request, f"Subject '{subject.name}' {verb}.")
    return redirect("scoring:subject_list")


def score_go(request, number):
    group = get_visible_group(request, number)
    try:
        subject_id = int(request.GET.get("subject", ""))
    except ValueError:
        return redirect("home")
    if not Subject.objects.filter(pk=subject_id).exists():
        return redirect("home")
    return redirect("scoring:score_grid", number=group.number, subject_id=subject_id)


def score_grid(request, number, subject_id):
    group = get_visible_group(request, number)
    subject = get_object_or_404(Subject, pk=subject_id)
    score_set = ScoreSet.objects.filter(
        instructor=request.user, subject=subject, group=group
    ).first()
    saved = {row.cadet_id: row for row in score_set.rows.all()} if score_set else {}
    rows = []
    for number_, cadet in enumerate(group.cadets.filter(is_active=True), start=1):
        saved_row = saved.get(cadet.pk)
        rows.append(
            {
                "number": number_,
                "cadet": cadet,
                "added": score_set is not None and saved_row is None,
                "cells": [
                    {
                        "field": field,
                        "name": f"s-{cadet.pk}-{field}",
                        "value": getattr(saved_row, field) if saved_row else None,
                    }
                    for field, _label, _header in ATTRIBUTES
                ],
                "comment": saved_row.comment if saved_row else "",
            }
        )
    return render(
        request,
        "scoring/score_grid.html",
        {
            "group": group,
            "subject": subject,
            "score_set": score_set,
            "rows": rows,
            "attributes": ATTRIBUTES,
            "score_choices": SCORE_CHOICES,
            "editable": group.is_editable,
        },
    )
