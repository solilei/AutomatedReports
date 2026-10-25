from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from audit import actions
from audit.service import log

from .forms import SubjectForm
from .models import Subject


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
