import time

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

from . import mfa
from .forms import PasswordSetForm
from .models import User

MFA_SESSION_KEYS = ("mfa_user_id", "mfa_started", "mfa_attempts", "mfa_next", "mfa_new_secret")
MFA_TIMEOUT_SECONDS = 300
MFA_MAX_ATTEMPTS = 5


def _safe_next(request, next_url):
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return ""


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
            user = form.get_user()
            next_url = _safe_next(request, request.POST.get("next", ""))
            if settings.MFA_REQUIRED:
                request.session["mfa_user_id"] = user.pk
                request.session["mfa_started"] = int(time.time())
                request.session["mfa_attempts"] = 0
                request.session["mfa_next"] = next_url
                return redirect("accounts:mfa_verify" if user.totp_confirmed else "accounts:mfa_setup")
            login(request, user)
            return redirect(next_url or "home")

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


def _clear_mfa(request):
    for key in MFA_SESSION_KEYS:
        request.session.pop(key, None)


def _pending_mfa_user(request):
    user_id = request.session.get("mfa_user_id")
    started = request.session.get("mfa_started")
    if user_id is None or started is None or time.time() - started > MFA_TIMEOUT_SECONDS:
        return None
    user = User.objects.filter(pk=user_id, is_active=True).first()
    return user


def _mfa_expired(request):
    _clear_mfa(request)
    messages.error(request, "Sign-in expired, please sign in again.")
    return redirect("accounts:login")


def _finish_mfa(request, user):
    next_url = request.session.get("mfa_next", "")
    _clear_mfa(request)
    login(request, user)
    return redirect(next_url or "home")


@login_not_required
def mfa_setup(request):
    user = _pending_mfa_user(request)
    if user is None:
        return _mfa_expired(request)
    if user.totp_confirmed:
        return redirect("accounts:mfa_verify")
    secret = request.session.setdefault("mfa_new_secret", mfa.new_secret())
    error = ""
    if request.method == "POST":
        if mfa.verify(secret, request.POST.get("code", "")):
            user.totp_secret = secret
            user.totp_confirmed = True
            user.save(update_fields=["totp_secret", "totp_confirmed"])
            log(user, actions.ACCOUNT_MFA_ENROLLED, f"{user.username} enrolled an authenticator app")
            return _finish_mfa(request, user)
        error = "Code not accepted, try again."
    return render(
        request,
        "accounts/mfa_setup.html",
        {"qr": mfa.qr_svg(mfa.provisioning_uri(secret, user.username)), "secret": secret, "error": error},
    )


@login_not_required
def mfa_verify(request):
    user = _pending_mfa_user(request)
    if user is None:
        return _mfa_expired(request)
    error = ""
    if request.method == "POST":
        if user.totp_confirmed and mfa.verify(user.totp_secret, request.POST.get("code", "")):
            return _finish_mfa(request, user)
        attempts = request.session.get("mfa_attempts", 0) + 1
        request.session["mfa_attempts"] = attempts
        if attempts >= MFA_MAX_ATTEMPTS:
            _clear_mfa(request)
            messages.error(request, "Too many attempts, please sign in again.")
            return redirect("accounts:login")
        error = "Code not accepted, try again."
    return render(request, "accounts/mfa_verify.html", {"error": error})
