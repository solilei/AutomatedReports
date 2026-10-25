import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit import actions
from audit.service import log

from . import mfa, services
from .decorators import admin_required
from .forms import PasswordSetForm, UserCreateForm
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


def _no_store(response):
    response["Cache-Control"] = "no-store"
    return response


@admin_required
def user_list(request):
    users = User.objects.order_by("is_approved", "username")
    return render(request, "accounts/user_list.html", {"users": users})


@admin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        role = form.cleaned_data["role"]
        password = services.generate_temp_password()
        user = User(
            username=username,
            full_name=form.cleaned_data["full_name"],
            role=role,
            auth_source=User.Source.LOCAL,
            is_approved=True,
            must_change_password=True,
        )
        user.set_password(password)
        user.save()
        log(
            request.user,
            actions.ACCOUNT_CREATED,
            f"Account '{username}' created as {role}",
            details={"username": username, "role": role},
        )
        return _no_store(render(request, "accounts/user_created.html", {"account": user, "password": password}))
    return render(request, "accounts/user_create.html", {"form": form})


def _row_action(request, pk, action, summary, apply):
    """Runs a POST-only row action; `apply` returns an error message or None after changing the target."""
    target = get_object_or_404(User, pk=pk)
    error = apply(target)
    if error:
        messages.error(request, error)
    else:
        log(request.user, action, summary.format(username=target.username), details={"username": target.username})
        messages.success(request, summary.format(username=target.username) + ".")
    return redirect("accounts:user_list")


@admin_required
@require_POST
def user_approve(request, pk):
    def apply(target):
        target.is_approved = True
        target.save(update_fields=["is_approved"])

    return _row_action(request, pk, actions.ACCOUNT_APPROVED, "Approved {username}", apply)


@admin_required
@require_POST
def user_promote(request, pk):
    def apply(target):
        if not target.is_approved:
            return "Approve the account first."
        target.role = User.Role.ADMIN
        target.save(update_fields=["role"])

    return _row_action(request, pk, actions.ACCOUNT_PROMOTED, "Promoted {username} to admin", apply)


@admin_required
@require_POST
def user_demote(request, pk):
    def apply(target):
        if services.is_last_admin(target):
            return "Cannot demote the last remaining admin."
        target.role = User.Role.INSTRUCTOR
        target.save(update_fields=["role"])

    return _row_action(request, pk, actions.ACCOUNT_DEMOTED, "Demoted {username} to instructor", apply)


@admin_required
@require_POST
def user_deactivate(request, pk):
    def apply(target):
        if target.pk == request.user.pk:
            return "You cannot deactivate your own account."
        if services.is_last_admin(target):
            return "Cannot deactivate the last remaining admin."
        target.is_active = False
        target.save(update_fields=["is_active"])

    return _row_action(request, pk, actions.ACCOUNT_DEACTIVATED, "Deactivated {username}", apply)


@admin_required
@require_POST
def user_reactivate(request, pk):
    def apply(target):
        target.is_active = True
        target.save(update_fields=["is_active"])

    return _row_action(request, pk, actions.ACCOUNT_REACTIVATED, "Reactivated {username}", apply)


@admin_required
@require_POST
def user_reset(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.auth_source != User.Source.LOCAL:
        raise PermissionDenied
    password = services.generate_temp_password()
    target.set_password(password)
    target.must_change_password = True
    target.totp_secret = ""
    target.totp_confirmed = False
    target.save(update_fields=["password", "must_change_password", "totp_secret", "totp_confirmed"])
    log(
        request.user,
        actions.ACCOUNT_RESET,
        f"Reset account '{target.username}'",
        details={"username": target.username},
    )
    return _no_store(render(request, "accounts/user_reset_done.html", {"account": target, "password": password}))
