from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit import actions
from audit.service import log

from .forms import PasswordSetForm


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


def pending(request):
    if request.user.is_approved:
        return redirect("home")
    return render(request, "accounts/pending.html")


def password_set(request):
    user = request.user
    if not user.must_change_password:
        return redirect("home")
    form = PasswordSetForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        log(user, actions.ACCOUNT_PASSWORD_SET, f"{user.username} set their password")
        messages.success(request, "Password set.")
        return redirect("home")
    return render(request, "accounts/password_set.html", {"form": form})
