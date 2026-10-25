from django.shortcuts import redirect, render

from accounts.decorators import admin_required
from audit import actions
from audit.service import log

from .forms import UploadForm
from .models import RosterUpload


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
        return redirect(f"/roster/upload/{record.pk}/columns/")
    return render(request, "roster/upload.html", {"form": form})
