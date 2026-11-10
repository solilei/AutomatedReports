import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit import actions
from audit.service import log

from . import mfa, microsoft, services
from .decorators import admin_required
from scoring.assignments import set_assignments

from .forms import PasswordSetForm, SubjectChecklistForm, UserCreateForm
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
    locked = False
    if request.method == "POST":
        if not show_local_form:
            return HttpResponseBadRequest("Local sign-in is disabled.")
        form = AuthenticationForm(request, data=request.POST)
        with transaction.atomic():
            account_id = (
                User.objects.filter(username=request.POST.get("username", ""))
                .values_list("pk", flat=True)
                .first()
            )
            account = services.lock_for_sign_in(account_id) if account_id else None
            locked = account is not None and services.is_sign_in_locked(account)
            if locked:
                # Unbound, so rendering never checks the password of a locked account.
                form = AuthenticationForm(request, initial={"username": account.username})
            elif form.is_valid():
                user = form.get_user()
                next_url = _safe_next(request, request.POST.get("next", ""))
                if settings.MFA_REQUIRED:
                    request.session["mfa_user_id"] = user.pk
                    request.session["mfa_started"] = int(time.time())
                    request.session["mfa_attempts"] = 0
                    request.session["mfa_next"] = next_url
                    return redirect(
                        "accounts:mfa_verify" if user.totp_confirmed else "accounts:mfa_setup"
                    )
                services.clear_failed_sign_ins(user)
                login(request, user)
                return redirect(next_url or "home")
            elif account is not None:
                services.record_failed_sign_in(account)

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "show_local_form": show_local_form,
            "show_microsoft": show_microsoft,
            "locked_message": services.LOCKED_MESSAGE if locked else "",
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


def _mfa_locked(request):
    _clear_mfa(request)
    messages.error(request, services.LOCKED_MESSAGE)
    return redirect("accounts:login")


def _finish_mfa(request, user):
    next_url = request.session.get("mfa_next", "")
    _clear_mfa(request)
    services.clear_failed_sign_ins(user)
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
    if services.is_sign_in_locked(user):
        return _mfa_locked(request)
    error = ""
    if request.method == "POST":
        with transaction.atomic():
            # Re-read under a row lock: a parallel attempt may have locked the account.
            user = services.lock_for_sign_in(user.pk)
            if services.is_sign_in_locked(user):
                return _mfa_locked(request)
            if user.totp_confirmed and mfa.verify(user.totp_secret, request.POST.get("code", "")):
                return _finish_mfa(request, user)
            services.record_failed_sign_in(user)
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
    users = User.objects.order_by("is_approved", "username").prefetch_related("assigned_subjects")
    return render(request, "accounts/user_list.html", {"users": users})


@admin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        role = User.Role.INSTRUCTOR
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
        with transaction.atomic():
            user.save()
            log(
                request.user,
                actions.ACCOUNT_CREATED,
                f"Account '{username}' created as {role}",
                details={"username": username, "role": role},
            )
            set_assignments(request.user, user, form.cleaned_data["subjects"])
        return _no_store(render(request, "accounts/user_created.html", {"account": user, "password": password}))
    return render(request, "accounts/user_create.html", {"form": form})


def _row_action(request, pk, action, summary, apply):
    """Runs a POST-only row action; `apply` returns an error message or None after changing the target."""
    with transaction.atomic():
        # Lock every admin row first so two admins demoting or deactivating each other
        # at once can't both pass the last-admin check.
        list(User.objects.select_for_update().filter(role=User.Role.ADMIN).order_by("pk"))
        target = get_object_or_404(User.objects.select_for_update(), pk=pk)
        error = apply(target)
        if not error:
            log(request.user, action, summary.format(username=target.username), details={"username": target.username})
    if error:
        messages.error(request, error)
    else:
        messages.success(request, summary.format(username=target.username) + ".")
    return redirect("accounts:user_list")


@admin_required
def user_approve(request, pk):
    target = get_object_or_404(User, pk=pk)
    form = SubjectChecklistForm(request.POST if request.method == "POST" else None, user=target)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            target = get_object_or_404(User.objects.select_for_update(), pk=pk)
            target.is_approved = True
            target.save(update_fields=["is_approved"])
            log(
                request.user,
                actions.ACCOUNT_APPROVED,
                f"Approved {target.username}",
                details={"username": target.username},
            )
            set_assignments(request.user, target, form.cleaned_data["subjects"])
        messages.success(request, f"Approved {target.username}.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_approve.html", {"form": form, "account": target})


@admin_required
def user_subjects(request, pk):
    target = get_object_or_404(User, pk=pk, is_approved=True)
    form = SubjectChecklistForm(request.POST if request.method == "POST" else None, user=target)
    if request.method == "POST" and form.is_valid():
        set_assignments(request.user, target, form.cleaned_data["subjects"])
        messages.success(request, f"Subjects saved for {target.username}.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_subjects.html", {"form": form, "account": target})


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
    target.failed_sign_ins = 0
    target.sign_in_locked_until = None
    target.save(
        update_fields=[
            "password",
            "must_change_password",
            "totp_secret",
            "totp_confirmed",
            "failed_sign_ins",
            "sign_in_locked_until",
        ]
    )
    log(
        request.user,
        actions.ACCOUNT_RESET,
        f"Reset account '{target.username}'",
        details={"username": target.username},
    )
    return _no_store(render(request, "accounts/user_reset_done.html", {"account": target, "password": password}))


def _microsoft_error(request, message, status):
    return render(request, "accounts/microsoft_error.html", {"message": message}, status=status)


@login_not_required
def microsoft_login(request):
    if settings.LOGIN_MODE == "local":
        raise Http404
    app = microsoft.build_msal_app()
    flow = app.initiate_auth_code_flow(microsoft.SCOPES, redirect_uri=settings.ENTRA_REDIRECT_URI)
    request.session["entra_flow"] = flow
    return redirect(flow["auth_uri"])


@login_not_required
def microsoft_callback(request):
    if settings.LOGIN_MODE == "local":
        raise Http404
    flow = request.session.pop("entra_flow", None)
    if flow is None:
        return _microsoft_error(request, "Sign-in session expired, please try again.", 400)
    try:
        result = microsoft.build_msal_app().acquire_token_by_auth_code_flow(flow, request.GET.dict())
    except ValueError:
        return _microsoft_error(request, "Microsoft sign-in failed.", 400)
    if "error" in result:
        return _microsoft_error(request, "Microsoft sign-in failed.", 400)
    claims = result["id_token_claims"]
    if claims.get("tid") != settings.ENTRA_TENANT_ID:
        return _microsoft_error(request, "Accounts from other organisations are not accepted.", 403)

    user = User.objects.filter(entra_object_id=claims["oid"]).first()
    if user is None:
        username = claims.get("preferred_username") or claims["oid"]
        if User.objects.filter(username=username).exists():
            return _microsoft_error(
                request, f"An account named {username} already exists. Ask an administrator.", 409
            )
        user = User(
            username=username,
            full_name=claims.get("name", ""),
            auth_source=User.Source.MICROSOFT,
            entra_object_id=claims["oid"],
            is_approved=False,
            role=User.Role.INSTRUCTOR,
        )
        user.set_unusable_password()
        user.save()
        log(
            None,
            actions.ACCOUNT_CREATED,
            f"Account '{username}' created on first Microsoft sign-in",
            details={"username": username, "role": user.role},
            actor_label="Microsoft first sign-in",
        )
    if not user.is_active:
        return _microsoft_error(request, "This account has been deactivated.", 403)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("home")
