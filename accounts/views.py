from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


@login_not_required
def login_view(request):
    show_local_form = settings.LOGIN_MODE in ("local", "both")
    show_microsoft = settings.LOGIN_MODE in ("microsoft", "both")

    if request.user.is_authenticated and request.method == "GET":
        return redirect("home")

    form = AuthenticationForm(request)
    if request.method == "POST":
        if not show_local_form:
            return HttpResponseBadRequest("Local sign-in is disabled.")
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            # Slice 6 replaces this branch when settings.MFA_REQUIRED is True.
            login(request, form.get_user())
            next_url = request.POST.get("next", "")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect("home")

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "show_local_form": show_local_form,
            "show_microsoft": show_microsoft,
            "next": request.GET.get("next", request.POST.get("next", "")),
        },
    )


@login_not_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")
