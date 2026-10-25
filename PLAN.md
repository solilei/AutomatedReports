# Implementation Plan — Cadet Soft Skills Report

Source of truth: `REQUIREMENTS.md`. Export layout: `report.md`. Sample data: `samples/sample_roster.xlsx`.

Work through the slices in order. Each slice builds only on the slices before it.

---

## Conventions (apply to every slice)

### Dependencies
`requirements.txt` is created in Slice 1 with exactly these pins. **Approved by the user on 2026-10-25.** No other slice adds a dependency.

```
Django==5.2.18
openpyxl==3.1.5
pyotp==2.10.0
segno==1.6.6
msal==1.39.0
```

| Package | Why |
|---|---|
| Django 5.2 (LTS) | Web framework |
| openpyxl | Read roster `.xlsx`, write report `.xlsx` |
| pyotp | TOTP codes for authenticator-app MFA |
| segno | QR code (inline SVG) for MFA setup; no other dependencies |
| msal | Microsoft Entra ID sign-in |

PostgreSQL support needs `psycopg`, which is **not** added in the PoC.

### Project layout
```
manage.py
requirements.txt
config/            settings.py, urls.py, wsgi.py, asgi.py
accounts/          users, login, MFA, Microsoft sign-in, account management
audit/             audit log
roster/            groups, cadets, roster upload, home page, group pages
scoring/           subjects, score sets, results, export
templates/base.html
static/css/site.css
```
- Every app has a `tests/` package (`tests/__init__.py` empty). Delete the `tests.py` and `admin.py` files that `startapp` creates. `django.contrib.admin` is **not** used.
- Templates live in `<app>/templates/<app>/`. `templates/base.html` is the only project-level template.
- Use only the Django ORM, with no raw SQL, so the database can switch to PostgreSQL.
- All state-changing actions are POST forms with `{% csrf_token %}`. GET never changes data.
- Show user feedback with `django.contrib.messages`.
- Use `django.core.exceptions.PermissionDenied` (HTTP 403) for role violations and `django.http.Http404` for objects that don't exist or are hidden.

### Commands
Every command assumes the venv is active: `source .venv/bin/activate`.

### "Done" for every slice (in addition to the slice's own criteria)
1. The slice's test command passes.
2. `python manage.py test` passes in full.
3. `python manage.py check` prints `System check identified no issues (0 silenced).`
4. `python manage.py makemigrations --check --dry-run` prints `No changes detected`.
5. Only the files listed in the slice were created or changed (plus generated migrations).
6. The slice's checkbox in this file is ticked.

Test files created by a slice are part of that slice. After the slice is done, don't modify them unless the user asks.

### Decisions taken in this plan (not stated in REQUIREMENTS.md; accepted by the user on 2026-10-25)
| # | Decision |
|---|---|
| D1 | Max roster upload size: **5 MB** (`ROSTER_MAX_UPLOAD_BYTES=5242880`). |
| D2 | Group numbers are stripped and upper-cased and must match `^[A-Z0-9._-]{1,20}$`. |
| D3 | Name matching (no ID column) is exact after collapsing whitespace. |
| D4 | A cadet who reappears in a re-upload after being inactive is **reactivated**. In ID mode, a changed name for a known ID is **renamed**. Both are shown in the preview. |
| D5 | A group's identity mode (ID or name) is fixed by its first upload. A later upload of that group with the other mode is rejected. |
| D6 | Uploads that include a locked, archived or deleted group number are rejected. |
| D7 | Averages are rounded half up to a **whole number** (no decimal places), so 2.5 → 3. The band and flag use that rounded value. Total = sum of the six whole-number averages (6–30). |
| D8 | A score set has one row per active cadet at save time. Cadets added later have no row in it and aren't counted for that set. A cadet with no rows in any set shows "no data". |
| D9 | "Added since your last save" = the instructor has a saved set for this group+subject and the cadet has no row in it. |
| D10 | MFA defaults **on** (`MFA_REQUIRED=1`). Turn it off for PoC testing with `MFA_REQUIRED=0`. When `DEBUG` is off, MFA is forced on. |
| D11 | Admins can **reset** a local account (new temporary password, MFA cleared), because there is no email. |
| D12 | Admins can **unarchive** a group (back to active). |
| D13 | Subjects can be added, renamed, deactivated and reactivated, but never deleted. Inactive subjects are hidden from the dropdown. |
| D14 | Admins can't deactivate their own account. |
| D15 | Locked and archived groups block scoring, roster re-upload and cadet deletion. Export and results stay available. |
| D16 | The template logo image is not reproduced in the export. |
| D17 | Instructor names in the export header use `full_name`, or `username` if `full_name` is blank. |
| D18 | Times are stored in UTC. Display time zone is `DJANGO_TIME_ZONE` (default `UTC`). |

---

## Slices

### [x] 1. Project scaffold, settings, custom user model

**Files**
- Create `requirements.txt` (exact content in Conventions).
- Run `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- Run `django-admin startproject config .`
- Run `python manage.py startapp accounts`, then `audit`, `roster`, `scoring`. In each app, delete `tests.py` and `admin.py` and create an empty `tests/__init__.py`.
- Change `config/settings.py`.
- Create `accounts/models.py`.
- Create `templates/` (empty dir with `.gitkeep`), `static/css/` (empty dir with `.gitkeep`).
- Create `accounts/tests/test_settings_and_user.py`.
- Generate `accounts/migrations/0001_initial.py` via `python manage.py makemigrations accounts`.

**Behaviour**
- `config/settings.py`:
  - Helper at top: `def env_bool(name, default): v = os.environ.get(name); return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}`.
  - `DEBUG = env_bool("DJANGO_DEBUG", True)`.
  - `SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")`. If it's missing and `DEBUG`, use `"dev-insecure-key-do-not-use-in-production"`. If it's missing and not `DEBUG`, raise `ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")`.
  - `ALLOWED_HOSTS`: if env `DJANGO_ALLOWED_HOSTS` is set, split it on commas and strip each entry. Otherwise use `["127.0.0.1", "localhost"]`.
  - `INSTALLED_APPS`: `django.contrib.auth`, `django.contrib.contenttypes`, `django.contrib.sessions`, `django.contrib.messages`, `django.contrib.staticfiles`, `accounts`, `audit`, `roster`, `scoring`. Remove `django.contrib.admin`. In `config/urls.py`, remove the admin import and route so `urlpatterns = []`.
  - `AUTH_USER_MODEL = "accounts.User"`.
  - `DATABASES`: if env `DB_ENGINE` is unset or `"sqlite"`, use `{"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}`. If `"postgresql"`, use `{"ENGINE": "django.db.backends.postgresql", "NAME": env DB_NAME, "USER": env DB_USER, "PASSWORD": env DB_PASSWORD, "HOST": env DB_HOST, "PORT": env DB_PORT default "5432"}`. Any other value raises `ImproperlyConfigured`.
  - `TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]`. `STATICFILES_DIRS = [BASE_DIR / "static"]`. `STATIC_URL = "static/"`.
  - `TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")`, `USE_TZ = True`, `LANGUAGE_CODE = "en-gb"`.
  - `AUTH_PASSWORD_VALIDATORS`: Django's four defaults, with `MinimumLengthValidator` `OPTIONS={"min_length": 12}`.
  - `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`.
- `accounts/models.py`: `class User(AbstractUser)` with:
  - `class Role(models.TextChoices): ADMIN = "admin", "Admin"; INSTRUCTOR = "instructor", "Instructor"`
  - `class Source(models.TextChoices): LOCAL = "local", "Local"; MICROSOFT = "microsoft", "Microsoft"`
  - `role = CharField(max_length=20, choices=Role.choices, default=Role.INSTRUCTOR)`
  - `auth_source = CharField(max_length=20, choices=Source.choices, default=Source.LOCAL)`
  - `full_name = CharField(max_length=150, blank=True)`
  - `is_approved = BooleanField(default=False)`
  - `must_change_password = BooleanField(default=False)`
  - `totp_secret = CharField(max_length=32, blank=True, default="")`
  - `totp_confirmed = BooleanField(default=False)`
  - `entra_object_id = CharField(max_length=36, unique=True, null=True, blank=True)`
  - property `is_admin` → `self.role == self.Role.ADMIN`
  - property `display_name` → `self.full_name or self.username`

**Tests** (`accounts/tests/test_settings_and_user.py`)
- `test_custom_user_model_is_active`: `get_user_model() is accounts.models.User`.
- `test_user_defaults`: a new user has role `instructor`, auth_source `local`, `is_approved` False, `must_change_password` False, `totp_confirmed` False, `entra_object_id` None.
- `test_is_admin_property`: True only for role `admin`.
- `test_display_name_falls_back_to_username`.
- `test_admin_site_not_installed`: `"django.contrib.admin" not in settings.INSTALLED_APPS`.
- `test_sqlite_is_default_engine`.

**Test command**: `python manage.py test accounts.tests.test_settings_and_user`

**Done**: All tests pass. `python manage.py migrate` runs on a fresh `db.sqlite3`. `python manage.py runserver` starts on `127.0.0.1:8000`.

---

### [x] 2. Audit log model and `log()` helper

**Files**
- Create `audit/actions.py`, `audit/models.py`, `audit/service.py`.
- Create `audit/tests/test_service.py`.
- Generate `audit/migrations/0001_initial.py`.

**Behaviour**
- `audit/actions.py`: one module-level string constant per action, plus `ACTION_CHOICES = [(a, a) for a in ALL_ACTIONS]`. `ALL_ACTIONS` is the list below, in this order:
  `account.created, account.approved, account.promoted, account.demoted, account.deactivated, account.reactivated, account.reset, account.password_set, account.mfa_enrolled, subject.created, subject.renamed, subject.deactivated, subject.reactivated, roster.uploaded, roster.applied, group.created, group.course_changed, group.locked, group.unlocked, group.archived, group.unarchived, group.deleted, cadet.added, cadet.renamed, cadet.deactivated, cadet.reactivated, cadet.deleted, score.changed, comment.changed, export.downloaded`.
  Constant names are upper-case with `.` replaced by `_` (e.g. `ACCOUNT_CREATED = "account.created"`).
- `audit/models.py`: `AuditEvent` with:
  - `timestamp = DateTimeField(auto_now_add=True, db_index=True)`
  - `actor = ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=SET_NULL, related_name="+")`
  - `actor_label = CharField(max_length=150)`
  - `action = CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)`
  - `group_number = CharField(max_length=20, blank=True, default="", db_index=True)`
  - `summary = CharField(max_length=500)`
  - `details = JSONField(default=dict, blank=True)`
  - `Meta.ordering = ["-timestamp", "-id"]`
  - `save()`: raise `ValueError("Audit events are immutable")` if `not self._state.adding`.
  - `delete()`: always raise `ValueError("Audit events cannot be deleted")`.
- `audit/service.py`: `def log(actor, action, summary, *, group_number="", details=None, actor_label=None) -> AuditEvent`.
  - `actor_label` defaults to `actor.username` if `actor` is set, else `"system"`.
  - `action` must be in `ALL_ACTIONS`, else raise `ValueError`.
  - `summary` is truncated to 500 characters.

**Tests** (`audit/tests/test_service.py`)
- `test_log_creates_event_with_actor_label`.
- `test_log_without_actor_uses_system_label`.
- `test_log_with_explicit_actor_label`.
- `test_unknown_action_raises`.
- `test_event_cannot_be_updated`.
- `test_event_cannot_be_deleted`.
- `test_events_ordered_newest_first`.
- `test_summary_truncated_to_500`.

**Test command**: `python manage.py test audit`

**Done**: All tests pass.

---

### [x] 3. Base layout, local login/logout, login mode, session rules

**Files**
- Change `config/settings.py`, `config/urls.py`.
- Create `accounts/urls.py`, `accounts/views.py`, `accounts/templates/accounts/login.html`.
- Create `templates/base.html`, `static/css/site.css`.
- Create `roster/views.py` (home placeholder), `roster/templates/roster/home.html`.
- Create `accounts/tests/helpers.py`, `accounts/tests/test_login.py`, `accounts/tests/test_security_settings.py`.

**Behaviour**
- Settings:
  - `LOGIN_MODE = os.environ.get("LOGIN_MODE", "local")`. If it's not one of `local`, `microsoft`, `both`, raise `ImproperlyConfigured`.
  - `MFA_REQUIRED = env_bool("MFA_REQUIRED", True)`. If `not DEBUG`, set `MFA_REQUIRED = True`.
  - `LOGIN_URL = "accounts:login"`, `LOGIN_REDIRECT_URL = "home"`.
  - `SESSION_COOKIE_AGE = 1800`, `SESSION_SAVE_EVERY_REQUEST = True`, `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`.
  - If `not DEBUG`: `SECURE_SSL_REDIRECT = True`, `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `SECURE_HSTS_SECONDS = 31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`, `SECURE_CONTENT_TYPE_NOSNIFF = True`.
  - `SESSION_COOKIE_HTTPONLY = True` (always).
  - `MIDDLEWARE` order: `SecurityMiddleware`, `SessionMiddleware`, `CommonMiddleware`, `CsrfViewMiddleware`, `AuthenticationMiddleware`, `MessageMiddleware`, `django.contrib.auth.middleware.LoginRequiredMiddleware`, `XFrameOptionsMiddleware`.
- `config/urls.py`: `path("", roster.views.home, name="home")`, `path("accounts/", include("accounts.urls"))`.
- `accounts/urls.py`: `app_name = "accounts"`; `login/` → `login_view` name `login`; `logout/` → `logout_view` name `logout`.
- `login_view` (decorated `@login_not_required`):
  - GET renders `accounts/login.html` with `show_local_form = LOGIN_MODE in ("local", "both")` and `show_microsoft = LOGIN_MODE in ("microsoft", "both")`. The Microsoft button links to `/accounts/microsoft/login/` as a literal href; the URL is added in Slice 8.
  - POST when `show_local_form` is False → `HttpResponseBadRequest("Local sign-in is disabled.")`.
  - POST uses `django.contrib.auth.forms.AuthenticationForm(request, data=request.POST)`. Invalid → re-render with the form errors.
  - Valid and `settings.MFA_REQUIRED` False → `login(request, user)`, then redirect to `next` if `url_has_allowed_host_and_scheme(next, allowed_hosts={request.get_host()})`, else to `home`.
  - Valid and `settings.MFA_REQUIRED` True → for now, behave the same as above. Slice 6 replaces this branch.
  - An authenticated user doing GET is redirected to `home`.
- `logout_view`: POST only (`@require_POST`) → `logout(request)` → redirect to `accounts:login`. Decorate `@login_not_required`.
- `roster.views.home`: renders `roster/home.html` with heading `Home`.
- `templates/base.html`: HTML5 doctype, `<title>{% block title %}Cadet Soft Skills{% endblock %}</title>`, links `{% static 'css/site.css' %}`.
  - Header has the site name "Cadet Soft Skills" and, when `user.is_authenticated`, a `<nav>` with a `Home` link, then `user.display_name` and a logout POST form (button "Sign out").
  - Messages render as `<ul class="messages">` with `<li class="{{ message.tags }}">`.
  - Then `{% block content %}{% endblock %}`.
- `static/css/site.css`, exactly:
  ```css
  body{font-family:system-ui,sans-serif;margin:0;background:#fff;color:#111}
  header{display:flex;gap:1rem;align-items:center;padding:.5rem 1rem;background:#1f2937;color:#fff}
  header a{color:#fff}
  main{padding:1rem}
  table{border-collapse:collapse}
  th,td{border:1px solid #999;padding:.25rem .5rem;text-align:left}
  .messages li.error{color:#b00}
  .messages li.success{color:#060}
  .messages li.warning{color:#a60}
  .band-5{background:#66FF33}.band-4{background:#C6E0B4}.band-3{background:#E2EFDA}.band-2{background:#FFC000}.band-1{background:#FF0000}
  .flag{color:#b00;font-weight:bold}
  .added-badge{background:#ffe08a;padding:0 .3rem;font-size:.8em}
  ```
- `accounts/tests/helpers.py`: `def make_user(username="inst", role="instructor", password="correct-horse-battery", **extra) -> User`. It creates an approved, active, local user with that password and sets any extra fields.

**Tests**
- `accounts/tests/test_login.py`, all with `@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")` unless stated:
  - `test_anonymous_redirected_to_login`: GET `/` → 302 to `/accounts/login/?next=/`.
  - `test_login_page_renders_local_form`.
  - `test_login_success_redirects_home`.
  - `test_login_respects_safe_next`.
  - `test_login_ignores_external_next`: `next=https://evil.example/` → redirect to `/`.
  - `test_login_wrong_password_shows_error`.
  - `test_inactive_user_cannot_login`.
  - `test_logout_requires_post`: GET → 405.
  - `test_logout_post_logs_out`.
  - `test_microsoft_mode_hides_local_form_and_rejects_post` (`LOGIN_MODE="microsoft"`): page has no password input; POST → 400.
  - `test_both_mode_shows_both`.
- `accounts/tests/test_security_settings.py`:
  - `test_session_idle_timeout_is_30_minutes`: `SESSION_COOKIE_AGE == 1800` and `SESSION_SAVE_EVERY_REQUEST is True`.
  - `test_default_login_mode_is_local` (reads `settings.LOGIN_MODE` with no override).
  - `test_allowed_hosts_default_localhost_only`.

**Test command**: `python manage.py test accounts.tests.test_login accounts.tests.test_security_settings`

**Done**: All tests pass. Manually: `runserver`, open `http://127.0.0.1:8000/`, and you're redirected to the login page.

---

### [x] 4. First admin from the command line

**Files**
- Create `accounts/management/__init__.py`, `accounts/management/commands/__init__.py`, `accounts/management/commands/createadmin.py`.
- Create `accounts/tests/test_createadmin.py`.

**Behaviour**
- `python manage.py createadmin --username <u> --full-name "<name>"`. Both options are required.
- If the username exists → `CommandError("User '<u>' already exists.")`.
- Creates a user with `role=admin`, `auth_source=local`, `is_approved=True`, `must_change_password=True`, `is_staff=False`, `is_superuser=False`.
- Generates a temporary password with `secrets.token_urlsafe(12)` and calls `set_password`.
- Prints exactly two lines to stdout: `Created admin '<u>'.` and `Temporary password (shown once): <password>`.
- Logs `audit.log(None, ACCOUNT_CREATED, "Admin '<u>' created from command line", actor_label="command line", details={"username": u, "role": "admin"})`. The password is never logged.

**Tests** (`accounts/tests/test_createadmin.py`, using `call_command` with `stdout=StringIO()`)
- `test_creates_approved_admin_needing_password_change`.
- `test_printed_password_works`: parse it from the output; `check_password` is True.
- `test_duplicate_username_raises_command_error`.
- `test_audit_event_written_without_password`: the password string doesn't appear in `summary` or `details`.

**Test command**: `python manage.py test accounts.tests.test_createadmin`

**Done**: All tests pass.

---

### [x] 5. Access gate (pending approval, forced password change) and role decorator

**Files**
- Create `accounts/middleware.py`, `accounts/decorators.py`, `accounts/forms.py`.
- Change `accounts/views.py`, `accounts/urls.py`, `config/settings.py` (add middleware).
- Create `accounts/templates/accounts/pending.html`, `accounts/templates/accounts/password_set.html`.
- Create `accounts/tests/test_gate.py`.

**Behaviour**
- `accounts/middleware.py` `AccessGateMiddleware`:
  - Insert it in `MIDDLEWARE` directly after `LoginRequiredMiddleware`.
  - For authenticated users only, resolve `request.path_info`. On `Resolver404`, return None.
  - If the URL's `view_name` is in `{"accounts:login", "accounts:logout", "accounts:pending", "accounts:password_set", "accounts:mfa_setup", "accounts:mfa_verify", "accounts:microsoft_login", "accounts:microsoft_callback"}`, return None.
  - Else if `not user.is_approved` → redirect to `accounts:pending`.
  - Else if `user.must_change_password` → redirect to `accounts:password_set`.
- `accounts/decorators.py`: `admin_required(view)` raises `PermissionDenied` unless `request.user.is_admin`. Login is already enforced by the middleware.
- `pending` view (`pending/`, name `pending`): renders "Your account is waiting for an administrator to approve it." plus the logout button. If the user is approved, redirect to `home`.
- `password_set` view (`password/set/`, name `password_set`):
  - Uses `django.contrib.auth.forms.SetPasswordForm(user)`.
  - On valid POST: save, set `must_change_password=False`, call `update_session_auth_hash`, log `ACCOUNT_PASSWORD_SET` (summary `"<username> set their password"`), add message "Password set.", redirect to `home`.
  - If `must_change_password` is already False, GET redirects to `home`.

**Tests** (`accounts/tests/test_gate.py`, `MFA_REQUIRED=False`)
- `test_unapproved_user_redirected_to_pending`.
- `test_pending_page_accessible_to_unapproved`.
- `test_approved_user_not_redirected_from_pending`: GET pending → 302 home.
- `test_must_change_password_redirects_to_password_set`.
- `test_password_set_clears_flag_and_keeps_session`: after POST, GET `/` → 200.
- `test_password_set_enforces_min_length_12`.
- `test_password_set_writes_audit_event`.
- `test_admin_required_403_for_instructor`: use a tiny view wrapped in `admin_required` via `RequestFactory`.
- `test_admin_required_allows_admin`.

**Test command**: `python manage.py test accounts.tests.test_gate`

**Done**: All tests pass.

---

### [x] 6. Authenticator-app MFA (TOTP) for local accounts

**Files**
- Create `accounts/mfa.py`.
- Change `accounts/views.py` (login branch plus two views), `accounts/urls.py`.
- Create `accounts/templates/accounts/mfa_setup.html`, `accounts/templates/accounts/mfa_verify.html`.
- Create `accounts/tests/test_mfa.py`.

**Behaviour**
- `accounts/mfa.py`:
  - `ISSUER = "Cadet Soft Skills"`
  - `new_secret()` → `pyotp.random_base32()`
  - `provisioning_uri(secret, username)` → `pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)`
  - `qr_svg(uri)` → `segno.make(uri).svg_inline(scale=4)`
  - `verify(secret, code)` → `pyotp.TOTP(secret).verify(code.strip(), valid_window=1)`
- Login view, valid credentials with `MFA_REQUIRED` True:
  - Don't call `login()` yet.
  - Store `session["mfa_user_id"] = user.pk`, `session["mfa_started"] = int(time.time())`, `session["mfa_attempts"] = 0`, `session["mfa_next"] = <safe next or "">`.
  - Redirect to `accounts:mfa_verify` if `user.totp_confirmed`, else to `accounts:mfa_setup`.
- Shared helper `_pending_mfa_user(request)`:
  - Returns the User for `mfa_user_id`.
  - Returns None if the key is missing, more than 300 seconds have passed since `mfa_started`, or the user is inactive.
  - On None, both views clear the `mfa_*` keys, add the error message "Sign-in expired, please sign in again.", and redirect to login.
- `mfa_setup` (`mfa/setup/`, `@login_not_required`):
  - If the pending user already has `totp_confirmed`, redirect to verify.
  - GET: put `new_secret()` in `session["mfa_new_secret"]` if it isn't there. Render the QR SVG (`{{ qr|safe }}`), the secret as text, and a 6-digit code input.
  - POST with a valid code: set `user.totp_secret = secret` and `user.totp_confirmed = True`, save, log `ACCOUNT_MFA_ENROLLED`, clear the `mfa_*` keys, `login()`, then redirect to `mfa_next` or `home`.
  - Invalid code → error "Code not accepted, try again."
- `mfa_verify` (`mfa/verify/`, `@login_not_required`):
  - POST with a valid code → clear the keys, `login()`, redirect.
  - Invalid → increment `mfa_attempts`. At 5 attempts, clear the keys, add the message "Too many attempts, please sign in again.", and redirect to login. Otherwise show the error "Code not accepted, try again."
- MFA applies only to `auth_source == local` users. Microsoft users never pass through these views.

**Tests** (`accounts/tests/test_mfa.py`, `@override_settings(MFA_REQUIRED=True, LOGIN_MODE="local")`)
- `test_login_without_mfa_enrolled_goes_to_setup_and_is_not_logged_in`.
- `test_setup_with_valid_code_enrolls_and_logs_in`: read the secret from the session; code is `pyotp.TOTP(secret).now()`.
- `test_setup_with_invalid_code_shows_error`.
- `test_enrolled_user_goes_to_verify`.
- `test_verify_valid_code_logs_in`.
- `test_verify_five_bad_codes_resets_sign_in`.
- `test_pending_mfa_expires_after_300_seconds`: patch `time.time`.
- `test_mfa_disabled_logs_in_directly` (`MFA_REQUIRED=False`).
- `test_mfa_forced_on_when_debug_off`: reload settings logic. Assert that `config.settings` computes True when `DJANGO_DEBUG=0` and `MFA_REQUIRED=0`, using `importlib.reload` under `mock.patch.dict(os.environ, {...})` with `DJANGO_SECRET_KEY` set. Afterwards, reload `config.settings` again with the original environment.

**Test command**: `python manage.py test accounts.tests.test_mfa`

**Done**: All tests pass. Manually, with `MFA_REQUIRED=1`: create an admin with `createadmin`, sign in, scan the QR with an authenticator app, sign in completes, and you're forced to set a password.

---

### [x] 7. Account management (admin)

**Files**
- Create `accounts/services.py`.
- Change `accounts/views.py`, `accounts/urls.py`, `accounts/forms.py`, `templates/base.html` (nav link).
- Create `accounts/templates/accounts/user_list.html`, `user_create.html`, `user_created.html`, `user_reset_done.html`.
- Create `accounts/tests/test_user_management.py`.

**Behaviour**
- `accounts/services.py`:
  - `active_admin_count()` = count of users with `role=admin`, `is_active=True`, `is_approved=True`.
  - `is_last_admin(user)` = `user.is_admin and user.is_active and user.is_approved and active_admin_count() <= 1`.
  - `generate_temp_password()` = `secrets.token_urlsafe(12)`.
- URLs. All are `admin_required`. Every row action is POST-only and redirects to `user_list` with a message.
  - `manage/` → `user_list`
  - `manage/new/` → `user_create`
  - `manage/<int:pk>/approve/` → `user_approve`
  - `manage/<int:pk>/promote/` → `user_promote`
  - `manage/<int:pk>/demote/` → `user_demote`
  - `manage/<int:pk>/deactivate/` → `user_deactivate`
  - `manage/<int:pk>/reactivate/` → `user_reactivate`
  - `manage/<int:pk>/reset/` → `user_reset`
- `user_list`:
  - Table columns: Username, Full name, Role, Sign-in (Local/Microsoft), Status (`Pending` if not approved; `Deactivated` if not active; else `Active`), MFA (`Yes`/`No`/`n/a` for Microsoft), Actions.
  - Order: pending first, then by username.
  - Which buttons each row shows:
    - Approve: pending only.
    - Promote: approved instructors.
    - Demote: admins.
    - Deactivate: active users other than yourself.
    - Reactivate: inactive users.
    - Reset: local users only.
- `user_create` (form fields `username`, `full_name`, `role` select Instructor/Admin):
  - Username is validated with `UnicodeUsernameValidator` and must be unique.
  - Creates a local, approved user with `must_change_password=True` and a temporary password.
  - Renders `user_created.html` directly (no redirect). It shows "Temporary password for <username>: <password>" and "This password is shown once. Give it to the user; they must change it at first sign-in."
  - The response has the header `Cache-Control: no-store`.
  - Logs `ACCOUNT_CREATED` with details `{"username", "role"}`.
- `user_approve`: sets `is_approved=True`; logs `ACCOUNT_APPROVED`.
- `user_promote`: sets `role=admin`; logs `ACCOUNT_PROMOTED`. Rejected with the error message "Approve the account first." if not approved.
- `user_demote`: if `is_last_admin(target)`, show the error "Cannot demote the last remaining admin." and make no change. Else set `role=instructor` and log `ACCOUNT_DEMOTED`.
- `user_deactivate`:
  - If target is yourself → error "You cannot deactivate your own account."
  - If `is_last_admin(target)` → error "Cannot deactivate the last remaining admin."
  - Else set `is_active=False` and log `ACCOUNT_DEACTIVATED`.
- `user_reactivate`: sets `is_active=True`; logs `ACCOUNT_REACTIVATED`.
- `user_reset` (local only, else 403):
  - New temporary password, `must_change_password=True`, `totp_secret=""`, `totp_confirmed=False`.
  - Renders `user_reset_done.html` with the password shown once and `Cache-Control: no-store`.
  - Logs `ACCOUNT_RESET`.
- No view anywhere lets a user change their own role.
- `base.html`: add an `Accounts` nav link (to `accounts:user_list`) shown when `user.is_admin`.

**Tests** (`accounts/tests/test_user_management.py`, `MFA_REQUIRED=False`)
- `test_instructor_gets_403_on_every_manage_url` (loop all 8 URLs).
- `test_create_local_user_shows_temp_password_once_and_sets_flags`.
- `test_created_user_can_login_with_temp_password_and_is_forced_to_set_password`.
- `test_create_duplicate_username_rejected`.
- `test_approve_pending_user`.
- `test_promote_requires_approval`.
- `test_promote_and_demote`.
- `test_cannot_demote_last_admin`.
- `test_cannot_deactivate_last_admin`.
- `test_cannot_deactivate_self`.
- `test_deactivated_user_cannot_login`.
- `test_deactivated_user_existing_session_is_ended`: force_login, deactivate, next GET `/` → redirect to login.
- `test_reset_clears_mfa_and_sets_new_temp_password`.
- `test_reset_not_allowed_for_microsoft_user`.
- `test_each_action_writes_expected_audit_action` (create, approve, promote, demote, deactivate, reactivate, reset).
- `test_get_on_action_url_returns_405`.

**Test command**: `python manage.py test accounts.tests.test_user_management`

**Done**: All tests pass.

---

### [ ] 8. Microsoft Entra ID sign-in (built, off by default)

**Files**
- Create `accounts/microsoft.py`.
- Change `config/settings.py`, `accounts/views.py`, `accounts/urls.py`.
- Create `accounts/templates/accounts/microsoft_error.html`.
- Create `accounts/tests/test_microsoft.py`.

**Behaviour**
- Settings: `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_REDIRECT_URI` read from env, default `""`. If `LOGIN_MODE in ("microsoft", "both")` and any of the four is empty, raise `ImproperlyConfigured("Microsoft sign-in needs ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET and ENTRA_REDIRECT_URI")`.
- `accounts/microsoft.py`:
  - `build_msal_app()` → `msal.ConfidentialClientApplication(settings.ENTRA_CLIENT_ID, authority=f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}", client_credential=settings.ENTRA_CLIENT_SECRET)`
  - `SCOPES = ["User.Read"]`
- Views use `from accounts import microsoft` and call `microsoft.build_msal_app()` so tests can patch it. Both views are `@login_not_required`.
- Both views raise `Http404` when `LOGIN_MODE == "local"`.
- `microsoft_login` (`microsoft/login/`): `flow = app.initiate_auth_code_flow(microsoft.SCOPES, redirect_uri=settings.ENTRA_REDIRECT_URI)`; `session["entra_flow"] = flow`; redirect to `flow["auth_uri"]`.
- `microsoft_callback` (`microsoft/callback/`):
  - `flow = session.pop("entra_flow", None)`. If missing → error page "Sign-in session expired, please try again." (400).
  - `result = app.acquire_token_by_auth_code_flow(flow, request.GET.dict())`. If `"error"` is in the result, or msal raises `ValueError` → error page "Microsoft sign-in failed." (400).
  - `claims = result["id_token_claims"]`. If `claims.get("tid") != settings.ENTRA_TENANT_ID` → error page "Accounts from other organisations are not accepted." (403).
  - Look up the user by `entra_object_id = claims["oid"]`.
    - If none exists, create one: `username = claims.get("preferred_username") or claims["oid"]`, `full_name = claims.get("name", "")`, `auth_source=microsoft`, `is_approved=False`, `role=instructor`, `set_unusable_password()`. Log `ACCOUNT_CREATED` with `actor_label="Microsoft first sign-in"`.
    - If the username is already taken by another user → error page "An account named <username> already exists. Ask an administrator." (409).
  - If the user is not `is_active` → error page "This account has been deactivated." (403).
  - `login(request, user, backend="django.contrib.auth.backends.ModelBackend")` → redirect to `home`. The gate sends unapproved users to `pending`.
- Microsoft users skip local MFA and never have a usable password.

**Tests** (`accounts/tests/test_microsoft.py`)
- Use `@override_settings(LOGIN_MODE="both", ENTRA_TENANT_ID="tenant-1", ENTRA_CLIENT_ID="c", ENTRA_CLIENT_SECRET="s", ENTRA_REDIRECT_URI="http://localhost:8000/accounts/microsoft/callback/", MFA_REQUIRED=False)`.
- Patch `accounts.microsoft.build_msal_app` to return a `mock.Mock`.
- Tests:
  - `test_routes_404_in_local_mode`.
  - `test_login_redirects_to_auth_uri_and_stores_flow`.
  - `test_first_sign_in_creates_pending_account_without_password`: user exists, `is_approved` False, `has_usable_password()` False, GET `/` → redirect pending.
  - `test_other_tenant_rejected_and_no_user_created`.
  - `test_existing_approved_user_signs_in`.
  - `test_deactivated_user_rejected`.
  - `test_missing_flow_in_session_returns_400`.
  - `test_msal_error_returns_400`.
  - `test_username_collision_returns_409`.
  - `test_admin_approval_grants_access`.
  - `test_missing_entra_settings_raise_improperly_configured`: reload settings with env `LOGIN_MODE=microsoft` and no `ENTRA_*`, then reload again with the original environment.

**Test command**: `python manage.py test accounts.tests.test_microsoft`

**Done**: All tests pass. The default `LOGIN_MODE=local` shows no Microsoft button, and the Microsoft routes return 404.

---

### [ ] 9. Subjects (model and admin management)

**Files**
- Create `scoring/models.py` (Subject only), `scoring/forms.py`, `scoring/views.py`, `scoring/urls.py`.
- Change `config/urls.py` (`path("", include("scoring.urls"))`), `templates/base.html` (nav link).
- Create `scoring/templates/scoring/subject_list.html`, `scoring/templates/scoring/subject_form.html`.
- Create `scoring/tests/test_subjects.py`.
- Generate `scoring/migrations/0001_initial.py`.

**Behaviour**
- `Subject`: `name = CharField(max_length=100, unique=True)`, `is_active = BooleanField(default=True)`, `Meta.ordering = ["name"]`, `__str__` returns name.
- `scoring/urls.py` (`app_name = "scoring"`), all `admin_required`:
  - `subjects/` → `subject_list`
  - `subjects/new/` → `subject_create`
  - `subjects/<int:pk>/edit/` → `subject_edit`
  - `subjects/<int:pk>/toggle/` → `subject_toggle` (POST only)
- `SubjectForm`: field `name`, stripped. Reject case-insensitive duplicates (`name__iexact`, excluding self) with "A subject with this name already exists."
- Create → log `SUBJECT_CREATED`. Rename → log `SUBJECT_RENAMED` with details `{"old", "new"}`. Toggle → `SUBJECT_DEACTIVATED` or `SUBJECT_REACTIVATED`.
- There is no delete view.
- `base.html`: `Subjects` nav link for admins.

**Tests** (`scoring/tests/test_subjects.py`)
- `test_instructor_forbidden`.
- `test_create_subject`.
- `test_duplicate_name_case_insensitive_rejected`.
- `test_rename_subject_logs_old_and_new`.
- `test_toggle_deactivates_and_reactivates`.
- `test_toggle_requires_post`.
- `test_no_delete_url_exists`: `reverse("scoring:subject_delete")` raises `NoReverseMatch`.

**Test command**: `python manage.py test scoring.tests.test_subjects`

**Done**: All tests pass.

---

### [ ] 10. Roster models and shared test helpers

**Files**
- Create `roster/models.py`.
- Create `roster/tests/helpers.py`, `roster/tests/test_models.py`.
- Generate `roster/migrations/0001_initial.py`.

**Behaviour**
- `Group`:
  - `number = CharField(max_length=20, unique=True)`
  - `course_number = CharField(max_length=50)`
  - `status = CharField(max_length=10, choices=Status.choices, default="active")` with `Status`: `ACTIVE="active"`, `LOCKED="locked"`, `ARCHIVED="archived"`
  - `identity_mode = CharField(max_length=4, choices=[("id", "Cadet ID"), ("name", "Name")])`
  - `created_at = DateTimeField(auto_now_add=True)`
  - `Meta.ordering = ["number"]`
  - property `is_editable` → `status == ACTIVE`
  - `__str__` → number
- `Cadet`:
  - `group = ForeignKey(Group, CASCADE, related_name="cadets")`
  - `name = CharField(max_length=200)`
  - `external_id = CharField(max_length=50, blank=True, default="")`
  - `is_active = BooleanField(default=True)`
  - `position = PositiveIntegerField()`
  - `Meta.ordering = ["position", "name"]`
  - Constraints: `UniqueConstraint(fields=["group", "external_id"], condition=~Q(external_id=""), name="unique_cadet_id_per_group")` and `UniqueConstraint(fields=["group", "name"], condition=Q(external_id=""), name="unique_cadet_name_per_group")`.
- `DeletedGroupNumber`: `number = CharField(max_length=20, unique=True)`, `deleted_at = DateTimeField(auto_now_add=True)`.
- `RosterColumnPreference`: `group_header`, `name_header`, `id_header` (each `CharField(max_length=200, blank=True, default="")`). Classmethod `get()` returns `get_or_create(pk=1)[0]`.
- `RosterUpload`:
  - `uploaded_by = ForeignKey(User, PROTECT)`
  - `uploaded_at = DateTimeField(auto_now_add=True)`
  - `original_filename = CharField(max_length=255)`
  - `file_content = BinaryField()`
  - `course_number = CharField(max_length=50)`
  - `status = CharField(max_length=10, choices=[("uploaded",)*2, ("parsed",)*2, ("applied",)*2], default="uploaded")`
  - `group_col = IntegerField(null=True)`, `name_col = IntegerField(null=True)`, `id_col = IntegerField(null=True)`
  - `parsed = JSONField(default=dict)`
- `roster/tests/helpers.py`:
  - `make_xlsx(rows: list[list]) -> bytes`: openpyxl workbook, first sheet, rows appended in order, saved to `BytesIO`.
  - `make_group(number="C216", cadets=("Alice Ng", "Bob Ray"), course_number="216.18", status="active", identity_mode="name") -> Group`: cadets get positions 1..n and an empty `external_id`.
  - `SAMPLE_ROSTER = settings.BASE_DIR / "samples" / "sample_roster.xlsx"`.

**Tests** (`roster/tests/test_models.py`)
- `test_group_number_unique`.
- `test_cadet_name_unique_per_group_without_id`.
- `test_same_name_allowed_with_different_ids`.
- `test_cadet_id_unique_per_group`.
- `test_cadets_ordered_by_position`.
- `test_column_preference_singleton`.
- `test_is_editable_only_when_active`.
- `test_make_xlsx_roundtrip`.

**Test command**: `python manage.py test roster.tests.test_models`

**Done**: All tests pass.

---

### [ ] 11. Roster upload step 1: file and course number

**Files**
- Create `roster/forms.py`, `roster/services.py` (reading functions only), `roster/urls.py`.
- Change `roster/views.py`, `config/settings.py` (`ROSTER_MAX_UPLOAD_BYTES = int(os.environ.get("ROSTER_MAX_UPLOAD_BYTES", 5242880))`), `config/urls.py` (`path("", include("roster.urls"))`), `templates/base.html` (nav link `Upload roster` for admins).
- Create `roster/templates/roster/upload.html`.
- Create `roster/tests/test_upload_file.py`.

**Behaviour**
- `roster/urls.py` (`app_name = "roster"`): `roster/upload/` → `upload` (`admin_required`).
- `UploadForm`: `file` (FileField), `course_number` (CharField max 50, stripped, required). The course number box always starts empty (no initial value, no pre-fill from earlier uploads). One course number per upload applies to every group in the file. Validation, in this order:
  1. The filename must end in `.xlsx` (case-insensitive), else "Only .xlsx files are accepted."
  2. `file.size <= settings.ROSTER_MAX_UPLOAD_BYTES`, else "File is larger than 5 MB." The MB figure comes from the setting: `size // 1048576`.
  3. `roster.services.read_sheet(content)` must succeed, else "File is not a valid .xlsx workbook."
  4. The header row must have at least two non-blank cells, else "The first row must contain column headers."
- `roster/services.py`:
  - `cell_text(v)`: `None` → `""`; `bool` → `str(v)`; `int` → `str(v)`; `float` → `str(int(v))` if `v.is_integer()` else `str(v)`; `datetime`/`date` → `v.date().isoformat()` / `v.isoformat()`; else `" ".join(str(v).split())`.
  - `read_sheet(content: bytes) -> tuple[list[str], list[list[str]]]`: `openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)`, uses `wb.worksheets[0]`, takes row 1 as headers, and returns all following rows. Every row is padded or truncated to the header length and converted with `cell_text`. Any exception is re-raised as `RosterError` (defined in the same module).
- On a valid POST:
  - Create `RosterUpload(uploaded_by=request.user, original_filename=<name>, file_content=<bytes>, course_number=...)`.
  - Log `ROSTER_UPLOADED` with details `{"filename", "size_bytes", "upload_id"}`.
  - Redirect to `/roster/upload/<id>/columns/`. That URL is a literal string here; it's created in Slice 12, where tests assert the redirect.

**Tests** (`roster/tests/test_upload_file.py`)
- `test_instructor_forbidden`.
- `test_rejects_non_xlsx_extension`.
- `test_rejects_oversize_file` (`override_settings(ROSTER_MAX_UPLOAD_BYTES=10)`).
- `test_rejects_corrupt_xlsx` (bytes `b"not a zip"` named `x.xlsx`).
- `test_rejects_missing_header_row`.
- `test_requires_course_number`.
- `test_course_number_starts_empty_after_previous_upload`: after one successful upload, GET the upload page; the `course_number` input has no value.
- `test_valid_upload_creates_staged_upload_and_redirects`.
- `test_valid_upload_logs_audit_event`.
- `test_read_sheet_converts_numbers_and_pads_rows`: `216.0` → `"216"`, short rows padded with `""`.
- `test_sample_roster_headers`: `read_sheet` of `SAMPLE_ROSTER` returns headers `["No.", "Cadet ID", "Full Name", "Course Group", "Sponsor", "Intake Date", "Email"]` and 44 data rows.

**Test command**: `python manage.py test roster.tests.test_upload_file`

**Done**: All tests pass.

---

### [ ] 12. Roster upload step 2: column choice, parsing, validation, remembered columns

**Files**
- Change `roster/services.py`, `roster/views.py`, `roster/urls.py`, `roster/forms.py`.
- Create `roster/templates/roster/upload_columns.html`.
- Create `roster/tests/test_upload_columns.py`.

**Behaviour**
- URL: `roster/upload/<int:pk>/columns/` → `upload_columns` (`admin_required`).
- If `upload.status == "applied"`: add the message "This upload has already been applied." and redirect to `roster:upload`.
- `ColumnForm(headers)` has three `ChoiceField`s with choices `(str(index), label)`:
  - `group_col` (required), `name_col` (required), `id_col` (optional, first choice `("", "— none —")`).
  - The label is the header text, or `"(column <Excel letter>, no header)"` for blank headers. Get the letter from `openpyxl.utils.get_column_letter(i + 1)`.
- Initial selection: for each field, the first column whose header equals (case-insensitive, stripped) the matching `RosterColumnPreference` header. No match means no initial value (for `id_col`, "— none —").
- The page shows a read-only table of the header row and the first 5 data rows.
- `roster/services.py` `parse_rows(rows, group_col, name_col, id_col) -> ParseResult`:
  - `ParseResult` is a dataclass with `groups: dict[str, list[dict]]` and `errors: list[str]`.
  - Each cadet dict is `{"name", "external_id", "row"}`.
  - The Excel row number = data index + 2.
  - Skip rows where the group, name and (if chosen) ID cells are all blank.
  - Group = `cell.strip().upper()`. Name = whitespace-collapsed.
  - Errors, all collected (not stop-at-first), each exactly:
    - `"Row {r}: group is blank."`
    - `"Row {r}: name is blank."`
    - `"Row {r}: cadet ID is blank."` (only when `id_col` is set)
    - `"Row {r}: group number '{g}' may only contain letters, digits, '.', '_' and '-' (max 20 characters)."`
    - ID mode only: `"Cadet ID '{id}' appears more than once in group {g} (rows {r1}, {r2}, …)."`
    - Name mode only: `"Group {g} has more than one cadet named '{name}' (rows {r1}, {r2}, …). Fix the file and upload it again."`
    - `"The file contains no cadets."` when no rows remain.
  - Group order and cadet order follow the order they first appear in the file.
- `check_groups(group_numbers, id_mode) -> list[str]`, errors exactly:
  - `"Group {g} is locked; unlock it before uploading."`
  - `"Group {g} is archived and its number cannot be reused."`
  - `"Group {g} was deleted and its number cannot be reused."`
  - `"Group {g} was first uploaded with a Cadet ID column; choose a Cadet ID column."`
  - `"Group {g} was first uploaded without a Cadet ID column; set Cadet ID to — none —."`
- POST:
  - If group_col equals name_col, or id_col equals either of them → form error "Group, Name and Cadet ID must be different columns."
  - Re-read the sheet from `file_content`, run `parse_rows`, then `check_groups`.
  - Any errors → re-render with the errors listed. Status and preference are unchanged.
  - Success → save `group_col`, `name_col`, `id_col` and `parsed = {"id_mode": bool, "groups": {...}}`, set `status="parsed"`. Save the three header texts to `RosterColumnPreference` (`id_header=""` when none). Redirect to `roster:upload_preview`. That route is created in Slice 13; until then define it in `roster/urls.py` pointing to a view that raises `Http404`, and Slice 13 replaces the view.

**Tests** (`roster/tests/test_upload_columns.py`)
- `test_shows_headers_as_choices`.
- `test_preselects_remembered_columns`.
- `test_same_column_twice_rejected`.
- `test_blank_group_and_name_rows_reported_with_row_numbers`.
- `test_fully_blank_rows_skipped`.
- `test_duplicate_names_without_id_rejected_with_rows`.
- `test_duplicate_names_allowed_with_id_column`.
- `test_duplicate_ids_rejected`.
- `test_invalid_group_number_rejected`.
- `test_group_number_uppercased`.
- `test_locked_archived_deleted_groups_rejected` (three subtests).
- `test_identity_mode_mismatch_rejected` (both directions).
- `test_success_saves_parsed_and_preference_and_redirects`.
- `test_sample_roster_parses_into_three_groups`: columns Course Group / Full Name / Cadet ID → `C216`: 15, `C217`: 13, `C218`: 16 cadets.
- `test_applied_upload_redirects`.

**Test command**: `python manage.py test roster.tests.test_upload_columns`

**Done**: All tests pass.

---

### [ ] 13. Roster upload step 3: preview and confirm

**Files**
- Change `roster/services.py`, `roster/views.py`, `roster/urls.py`.
- Create `roster/templates/roster/upload_preview.html`.
- Create `roster/tests/test_upload_apply.py`.

**Behaviour**
- `build_preview(upload) -> list[GroupChange]`. `GroupChange` is a dataclass with:
  - `number`, `is_new`, `course_old` (None if new), `course_new`
  - `added: list[str]`
  - `deactivated: list[str]` (active cadets in the DB who are missing from the file)
  - `reactivated: list[str]` (inactive cadets in the DB who appear in the file)
  - `renamed: list[tuple[str, str]]` (ID mode only: same ID, different name)
  - `unchanged: int`
- Matching: ID mode matches `(group, external_id)`; name mode matches `(group, name)`.
- `upload_preview` view (`roster/upload/<int:pk>/preview/`, `admin_required`):
  - Status `uploaded` → redirect to columns. Status `applied` → message plus redirect to `roster:upload`.
  - GET runs `check_groups` again and shows any errors.
  - It shows each group as a section: `New group` or `Existing group`, course number (`old → new` if changed), and lists titled `Cadets added`, `Cadets no longer present (will be marked inactive, data kept)`, `Cadets returning (will be reactivated)`, `Cadets renamed`, plus `Unchanged: N`.
  - The `Confirm and apply` button POSTs. A `Cancel` link goes to `roster:upload`.
- POST:
  - Re-run `check_groups`. On errors, re-render without applying.
  - Otherwise apply in `transaction.atomic()`:
    - Create the group with `identity_mode` and `course_number`, and log `GROUP_CREATED`. Or, for an existing group with a different course number, update it and log `GROUP_COURSE_CHANGED` with `{"old", "new"}`.
    - Every cadet in the file gets `position` = its 1-based index within its group in the file.
    - Add new cadets (`CADET_ADDED`). Reactivate returning ones (`CADET_REACTIVATED`). Rename (`CADET_RENAMED` `{"old", "new"}`). Set missing active cadets `is_active=False` (`CADET_DEACTIVATED`).
    - Every cadet event sets `group_number` and `details={"cadet": name, "external_id": id}`.
    - Never delete a row.
    - Set `status="applied"`, `file_content=b""`, `parsed={}`.
    - Log `ROSTER_APPLIED` with summary `"Applied roster '<filename>' to groups C216, C217"` and details `{"upload_id", "groups": [...]}`.
  - Add the message "Roster applied." and redirect to `home`.

**Tests** (`roster/tests/test_upload_apply.py`)
- `test_preview_lists_new_groups_and_counts`.
- `test_nothing_changes_before_confirm`: after GET preview, `Group.objects.count() == 0`.
- `test_confirm_creates_groups_and_cadets_with_positions_and_course`.
- `test_reupload_adds_and_deactivates_but_never_deletes`: Cadet count before and after includes the deactivated cadet.
- `test_reupload_reactivates_returning_cadet`.
- `test_reupload_id_mode_renames`.
- `test_reupload_updates_course_number_and_logs`.
- `test_confirm_twice_does_not_reapply`.
- `test_group_locked_between_preview_and_confirm_blocks_apply`.
- `test_file_content_cleared_after_apply`.
- `test_audit_events_written_for_each_change`.
- `test_sample_roster_end_to_end`: upload → columns → confirm gives 3 groups and 44 active cadets.

**Test command**: `python manage.py test roster.tests.test_upload_apply`

**Done**: All tests pass. Manually: upload `samples/sample_roster.xlsx` through the browser and see 3 groups created.

---

### [ ] 14. Scoring models and attribute definitions

**Files**
- Create `scoring/attributes.py`.
- Change `scoring/models.py`.
- Create `scoring/tests/helpers.py`, `scoring/tests/test_models.py`.
- Generate the migration.

**Behaviour**
- `scoring/attributes.py`:
  ```python
  ATTRIBUTES = [
      ("attentiveness", "Attentiveness / Engagement", "Attentiveness Engagement"),
      ("motivation", "Motivation / Diligence / Enthusiasm", "Motivation Diligence Enthusiasm"),
      ("discipline", "Discipline / Courtesy", "Discipline Courtesy"),
      ("attire", "Attire / Appearance", "Attire Appearance"),
      ("teamwork", "Teamwork", "Teamwork"),
      ("communication", "Communication / Participation / Interaction", "Comms. Participation Interaction"),
  ]
  ATTRIBUTE_FIELDS = [a[0] for a in ATTRIBUTES]
  SCORE_CHOICES = [(5, "5 – A Excellent"), (4, "4 – B Above standard"), (3, "3 – C Meets standard"), (2, "2 – D Below standard"), (1, "1 – E Unacceptable")]
  BLANK_COUNTS_AS = 3
  ```
- `ScoreSet`:
  - `instructor = ForeignKey(User, PROTECT, related_name="score_sets")`
  - `subject = ForeignKey(Subject, PROTECT)`
  - `group = ForeignKey("roster.Group", CASCADE, related_name="score_sets")`
  - `created_at = DateTimeField(auto_now_add=True)`, `updated_at = DateTimeField(auto_now=True)`
  - `UniqueConstraint(fields=["instructor", "subject", "group"], name="unique_score_set")`
- `CadetScore`:
  - `score_set = ForeignKey(ScoreSet, CASCADE, related_name="rows")`
  - `cadet = ForeignKey("roster.Cadet", CASCADE, related_name="scores")`
  - Six `PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])` named as `ATTRIBUTE_FIELDS`
  - `comment = TextField(blank=True, default="")`
  - `UniqueConstraint(fields=["score_set", "cadet"], name="unique_row_per_cadet")`
  - One `CheckConstraint` per attribute: `Q(<f>__isnull=True) | Q(<f>__gte=1, <f>__lte=5)`, named `"<f>_1_to_5"`.
- `scoring/tests/helpers.py`: `make_score_set(instructor, subject, group, rows: dict[Cadet, dict]) -> ScoreSet`. It creates the set and one `CadetScore` per entry with the given field values.

**Tests** (`scoring/tests/test_models.py`)
- `test_one_score_set_per_instructor_subject_group`.
- `test_same_instructor_two_subjects_two_sets`.
- `test_score_out_of_range_rejected_by_db` (`IntegrityError` on 6 and 0).
- `test_blank_scores_allowed`.
- `test_deleting_group_cascades_to_sets_and_rows`.
- `test_deleting_cadet_cascades_to_rows`.
- `test_instructor_delete_protected`.

**Test command**: `python manage.py test scoring.tests.test_models`

**Done**: All tests pass.

---

### [ ] 15. Score grid: view (GET)

**Files**
- Create `scoring/access.py`.
- Change `scoring/views.py`, `scoring/urls.py`.
- Create `scoring/templates/scoring/score_grid.html`.
- Create `scoring/tests/test_grid_view.py`.

**Behaviour**
- `scoring/access.py` `get_visible_group(request, number) -> Group`:
  - Raises `Http404` if the group doesn't exist.
  - Raises `Http404` if `status == archived` and the user isn't an admin.
- URLs:
  - `groups/<str:number>/score/` → `score_go`. GET with `?subject=<id>` redirects to `score_grid`. A missing or invalid subject redirects to `roster:group_detail`; that route is created in Slice 17, so until then redirect to `home`, and Slice 17 changes it.
  - `groups/<str:number>/score/<int:subject_id>/` → `score_grid`.
- `score_grid` GET:
  - Loads the group via `get_visible_group`, the subject (404 if missing), and `ScoreSet.objects.filter(instructor=request.user, subject=subject, group=group).first()`.
  - Rows = the group's active cadets in `(position, name)` order, numbered 1..n.
  - Each row has: No., Name, six `<select name="s-<cadet_pk>-<field>">` (options `""` blank plus `SCORE_CHOICES`, with the existing value selected), and `<textarea name="c-<cadet_pk>" maxlength="1000" rows="1">`.
  - If a set exists and the cadet has no row in it, show `<span class="added-badge">added since your last save</span>` after the name.
  - Header shows group number, course number, subject name, and "Last saved: <updated_at local>" or "Not saved yet".
  - If `group.is_editable` is False: every input is `disabled`, there's no Save button, and a banner says "This group is <status> and read-only."
- An instructor only ever sees their own set. There's no parameter to view another instructor's set here.

**Tests** (`scoring/tests/test_grid_view.py`)
- `test_lists_only_active_cadets_in_order`.
- `test_prefills_own_existing_scores`.
- `test_does_not_show_other_instructors_scores`.
- `test_added_since_last_save_badge`.
- `test_no_badge_when_no_saved_set`.
- `test_locked_group_is_read_only`.
- `test_archived_group_404_for_instructor_readonly_for_admin`.
- `test_unknown_group_or_subject_404`.
- `test_score_go_redirects_to_grid`.

**Test command**: `python manage.py test scoring.tests.test_grid_view`

**Done**: All tests pass.

---

### [ ] 16. Score grid: save (POST), blank warning, audit

**Files**
- Create `scoring/services.py`.
- Change `scoring/views.py`, `scoring/templates/scoring/score_grid.html`.
- Create `scoring/tests/test_grid_save.py`.

**Behaviour**
- POST when `not group.is_editable` → `PermissionDenied`.
- Parse only the active cadets of the group. Field values must be `""` or `"1"`–`"5"`.
  - Otherwise show the error `"Invalid score for {cadet name} / {attribute label}."`.
  - A comment longer than 1000 characters (after strip) gives `"Comment for {cadet name} is longer than 1000 characters."`.
  - Errors re-render the grid with the submitted values and save nothing.
- If no score is entered in any cell → error "Enter at least one score before saving." Nothing is saved.
- `blank_cells` = number of blank score cells; `blank_cadets` = cadets with at least one blank cell. If `blank_cells > 0` and `request.POST.get("confirm_blanks") != str(blank_cells)`:
  - Re-render with the submitted values.
  - Show the warning `"{blank_cells} blank cell(s) across {blank_cadets} cadet(s) will be counted as 3. Click Save again to confirm."`.
  - Add a hidden input `confirm_blanks` with value `blank_cells`.
  - Save nothing.
- Otherwise call `scoring.services.save_score_set(instructor, subject, group, data)` inside `transaction.atomic()`:
  - `get_or_create` the ScoreSet.
  - For each active cadet, `get_or_create` its CadetScore. For each attribute, if old != new, set it and log `SCORE_CHANGED` with summary `"{instructor} changed {attribute label} for {cadet} ({subject}): {old or 'blank'} → {new or 'blank'}"` and details `{"cadet_id", "cadet", "subject", "attribute", "old", "new", "score_set_id"}`.
  - If the comment changed, log `COMMENT_CHANGED` with details `{"cadet_id", "cadet", "subject", "old", "new", "score_set_id"}`.
  - All events carry `group_number`.
  - Always call `score_set.save()` so `updated_at` is refreshed.
- On success: message "Saved." and redirect to the same grid (GET).

**Tests** (`scoring/tests/test_grid_save.py`)
- `test_save_requires_at_least_one_score`.
- `test_invalid_score_value_rejected`.
- `test_long_comment_rejected`.
- `test_blank_warning_shown_and_nothing_saved`.
- `test_confirm_with_matching_count_saves`.
- `test_confirm_with_stale_count_warns_again`.
- `test_full_grid_saves_without_warning`.
- `test_rows_created_for_every_active_cadet_including_all_blank`.
- `test_edit_updates_existing_set_not_new_one`.
- `test_score_change_audit_has_old_and_new`.
- `test_unchanged_values_not_logged`.
- `test_comment_change_logged`.
- `test_locked_group_post_forbidden`.
- `test_inactive_cadet_fields_ignored`.
- `test_badge_cleared_after_save`.

**Test command**: `python manage.py test scoring.tests.test_grid_save`

**Done**: All tests pass. Manually: score a group in the browser, leave cells blank, see the warning, then confirm.

---

### [ ] 17. Home group dropdown, group page, admin group list

**Files**
- Change `roster/views.py`, `roster/urls.py`, `roster/templates/roster/home.html`.
- Change `scoring/views.py` (`score_go` fallback redirect → `roster:group_detail`).
- Change `scoring/templates/scoring/score_grid.html` (add a link `← Group <number>` to `roster:group_detail`).
- Change `templates/base.html` (nav `Groups` for admins).
- Create `roster/templates/roster/group_detail.html`, `roster/templates/roster/group_list.html`.
- Create `roster/tests/test_group_pages.py`.

**Behaviour**
- `home`: a GET form to `roster:group_go`. Its `<select name="number">` lists groups with status `active` or `locked`, ordered by number, with labels `"C216 (course 216.18)"` plus `" — locked"` when locked. Button "Open". If there are no groups, show "No groups yet." and, for admins, a link to upload a roster.
- `groups/go/` → `group_go`: redirects to `group_detail` for `?number=` (upper-cased). An unknown number → message "Group not found." and redirect home.
- `groups/<str:number>/` → `group_detail` (uses `scoring.access.get_visible_group`):
  - Shows the number, course number, status and active cadet count.
  - A subject GET form to `scoring:score_go` with `<select name="subject">` of active subjects. Button "Score".
  - "My score sets for this group": the user's sets with subject and last-saved time, each linking to its grid.
- `groups/` → `group_list` (`admin_required`): table of all groups including archived, with columns Number, Course, Status, Active cadets, Inactive cadets, Score sets. Each number links to its group page.

**Tests** (`roster/tests/test_group_pages.py`)
- `test_home_dropdown_lists_active_and_locked_not_archived`.
- `test_group_go_redirects`.
- `test_group_go_unknown_number`.
- `test_group_detail_subject_dropdown_only_active_subjects`.
- `test_group_detail_lists_only_my_score_sets`.
- `test_archived_group_detail_404_for_instructor`.
- `test_group_list_admin_only_and_includes_archived`.

**Test command**: `python manage.py test roster.tests.test_group_pages`

**Done**: All tests pass. Manually: Home → pick group → pick subject → score.

---

### [ ] 18. Group lifecycle: lock, unlock, archive, unarchive, delete

**Files**
- Create `roster/lifecycle.py`.
- Change `roster/views.py`, `roster/urls.py`, `roster/templates/roster/group_detail.html` (admin buttons), `roster/templates/roster/group_list.html`.
- Create `roster/templates/roster/group_delete_confirm.html`.
- Create `roster/tests/test_lifecycle.py`.

**Behaviour**
- URLs under `groups/<str:number>/`: `lock/`, `unlock/`, `archive/`, `unarchive/` (POST only), `delete/` (GET shows the confirm page, POST deletes). All `admin_required`. Names `group_lock`, `group_unlock`, `group_archive`, `group_unarchive`, `group_delete`.
- Allowed transitions. Anything else → error message `"Cannot {action} a group that is {status}."`, no change.
  - lock: active → locked (`GROUP_LOCKED`)
  - unlock: locked → active (`GROUP_UNLOCKED`)
  - archive: active or locked → archived (`GROUP_ARCHIVED`)
  - unarchive: archived → active (`GROUP_UNARCHIVED`)
  - delete: archived only. POST field `confirm_number` must equal the group number exactly, else error "Type the group number to confirm."
- Delete runs in `transaction.atomic()`: create `DeletedGroupNumber(number)`, log `GROUP_DELETED` with details `{"course_number", "cadets": count, "score_sets": count}`, then `group.delete()` (cascades). Audit events are kept.
- Buttons on the group page are shown per allowed transition. The Delete link is only shown when archived.

**Tests** (`roster/tests/test_lifecycle.py`)
- `test_instructor_forbidden_for_all_actions`.
- `test_lock_unlock`.
- `test_locked_group_rejects_scoring_post` (reuse grid POST).
- `test_archive_from_active_and_locked`.
- `test_archived_hidden_from_home_dropdown`.
- `test_unarchive`.
- `test_invalid_transition_no_change`.
- `test_delete_requires_archived`.
- `test_delete_requires_typed_number`.
- `test_delete_removes_group_data_and_records_number`.
- `test_deleted_number_cannot_be_reused_by_upload`.
- `test_audit_events_kept_after_delete`.

**Test command**: `python manage.py test roster.tests.test_lifecycle`

**Done**: All tests pass.

---

### [ ] 19. Cadet management and permanent cadet deletion

**Files**
- Change `roster/views.py`, `roster/urls.py`, `roster/templates/roster/group_detail.html` (admin link "Manage cadets").
- Create `roster/templates/roster/cadet_list.html`, `roster/templates/roster/cadet_delete_confirm.html`.
- Create `roster/tests/test_cadets.py`.

**Behaviour**
- `groups/<str:number>/cadets/` → `cadet_list` (`admin_required`): every cadet including inactive, with columns Position, Name, Cadet ID, Status (Active/Inactive), score rows count, and a Delete link.
- `cadets/<int:pk>/delete/` → `cadet_delete` (`admin_required`):
  - GET shows "Permanently delete <name> from <group> and all <n> of their scores? This cannot be undone."
  - POST deletes the cadet (cascade) and logs `CADET_DELETED` with details `{"cadet", "external_id", "score_rows": n}`, then redirects to `cadet_list`.
  - If the group is not editable (locked or archived) → error message "Group is <status>; cadets cannot be deleted." and no deletion.

**Tests** (`roster/tests/test_cadets.py`)
- `test_instructor_forbidden`.
- `test_list_includes_inactive`.
- `test_get_does_not_delete`.
- `test_post_deletes_cadet_and_scores_and_logs`.
- `test_locked_group_blocks_delete`.

**Test command**: `python manage.py test roster.tests.test_cadets`

**Done**: All tests pass.

---

### [ ] 20. "My score sets" and admin score-set views

**Files**
- Change `scoring/views.py`, `scoring/urls.py`, `templates/base.html` (nav `My score sets`), `roster/templates/roster/group_detail.html` (admin link "All score sets").
- Create `scoring/templates/scoring/my_score_sets.html`, `scoring/templates/scoring/group_score_sets.html`, `scoring/templates/scoring/score_set_detail.html`.
- Create `scoring/tests/test_score_set_views.py`.

**Behaviour**
- `my-score-sets/` → `my_score_sets`: the user's sets. Archived groups are excluded unless the user is an admin. Columns: Group, Subject, Last saved, link "Open" (to the grid). Ordered by `-updated_at`.
- `groups/<str:number>/score-sets/` → `group_score_sets` (`admin_required`): all sets for the group, with columns Instructor (display name, plus " (deactivated)" when inactive), Subject, Last saved, link "View".
- `score-sets/<int:pk>/` → `score_set_detail` (`admin_required`): read-only table with No., Name, the six values (blank shown as `—`) and the comment, for every row in the set, active cadets first then inactive ones marked "(inactive)".

**Tests** (`scoring/tests/test_score_set_views.py`)
- `test_my_score_sets_only_mine`.
- `test_group_score_sets_admin_only`.
- `test_score_set_detail_admin_only`.
- `test_instructor_cannot_view_other_set_by_id` (403).
- `test_deactivated_instructor_marked`.

**Test command**: `python manage.py test scoring.tests.test_score_set_views`

**Done**: All tests pass.

---

### [ ] 21. Results calculation (pure logic)

**Files**
- Create `scoring/results.py`.
- Create `scoring/tests/test_results.py`.

**Behaviour**
```python
BAND_HEX = {5: "66FF33", 4: "C6E0B4", 3: "E2EFDA", 2: "FFC000", 1: "FF0000"}
FLAG_BELOW = 3  # a rounded average below C (3) is flagged

def round_average(total: int, count: int) -> int:
    return int((Decimal(total) / Decimal(count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

@dataclass(frozen=True)
class CadetResult:
    number: int
    cadet: Cadet
    averages: dict[str, int] | None   # whole numbers 1-5; None = no data. The value is also the band.
    total: int | None                 # 6-30
    flagged: bool

def group_results(group) -> list[CadetResult]
```
- Uses active cadets only, in `(position, name)` order, numbered 1..n.
- For each cadet, collect every `CadetScore` row for that cadet in score sets of that group, from all instructors and subjects, including deactivated instructors.
- Per attribute: average = `round_average(sum(v if v is not None else 3 for each row), len(rows))`, which rounds half up to a whole number (2.5 → 3).
- The band of an average is the average itself, and its colour is `BAND_HEX[average]`.
- `total` = the sum of the six whole-number averages.
- `flagged` = any average `< FLAG_BELOW`. This is the same as an unrounded average below 2.5.
- No rows at all → `averages` and `total` are None, and `flagged` is False.
- Uses exactly 2 queries regardless of cadet count: one for the active cadets, one for the rows via `CadetScore.objects.filter(score_set__group=group, cadet__in=cadets)`.

**Tests** (`scoring/tests/test_results.py`)
- `test_single_set_averages_equal_scores`.
- `test_average_across_instructors_and_subjects`.
- `test_blank_in_saved_set_counts_as_3`.
- `test_cadet_without_rows_is_no_data`.
- `test_cadet_added_after_save_not_counted_for_that_set`.
- `test_inactive_cadets_excluded`.
- `test_round_average_half_up_to_whole_number`: `round_average(5, 2) == 3` (2.5), `round_average(7, 3) == 2` (2.33), `round_average(5, 3) == 2` (1.67), `round_average(9, 2) == 5` (4.5), `round_average(13, 3) == 4` (4.33).
- `test_averages_are_ints`.
- `test_flag_when_any_average_below_2_5`: one attribute scored 2, 2, 3 → average 2 → flagged.
- `test_not_flagged_at_exactly_2_5`: one attribute scored 2, 3 → average 3 → not flagged.
- `test_total_is_sum_of_whole_number_averages_range_6_to_30`.
- `test_deactivated_instructor_scores_still_count`.
- `test_query_count_constant`: `assertNumQueries(2)` with 5 cadets and again with 20 cadets.

**Test command**: `python manage.py test scoring.tests.test_results`

**Done**: All tests pass.

---

### [ ] 22. Results page

**Files**
- Change `scoring/views.py`, `scoring/urls.py`, `roster/templates/roster/group_detail.html` (link "Results").
- Create `scoring/templates/scoring/results.html`.
- Create `scoring/tests/test_results_page.py`.

**Behaviour**
- `groups/<str:number>/results/` → `results`. Any approved user can open it (archived groups for admins only, via `get_visible_group`).
- Table header: `No.`, `Name`, the six attribute labels, `Total`.
- Each row:
  - Average cells show the whole number (no decimal places) with `class="band-<average>"`.
  - The Total cell shows the whole-number total.
  - Flagged rows have the class `flagged` and, after the name, `<span class="flag">Below C – HGS consultation</span>`.
  - No-data rows show the name and one cell `colspan="7"` with `no data`.
- Above the table: `Based on N saved score set(s).` and a key listing the 5 bands with their colours and labels `5 A Excellent … 1 E Unacceptable`.
- Instructors see only the averages. No per-instructor data appears on this page.

**Tests** (`scoring/tests/test_results_page.py`)
- `test_columns_and_order`.
- `test_values_whole_numbers_and_band_classes`: no `.` appears in any average or total cell.
- `test_no_data_row`.
- `test_flag_marker`.
- `test_inactive_cadets_hidden`.
- `test_page_does_not_contain_instructor_names` (an instructor viewing it doesn't see the other instructor's username or full name).
- `test_archived_group_admin_only`.

**Test command**: `python manage.py test scoring.tests.test_results_page`

**Done**: All tests pass.

---

### [ ] 23. Export workbook builder

**Files**
- Create `scoring/export.py`.
- Create `scoring/tests/test_export_builder.py`.

**Behaviour**
`build_group_report(group, export_date: date) -> openpyxl.Workbook`. One sheet, title = `group.number`. Specification, row by row:

| Cells | Content | Format |
|---|---|---|
| Column widths | A 3.82, B 29.73, C–N 8.36, O 6.73 | |
| A1:B3 merged | `Course {course_number}` | bold, vertical center |
| D1 | `Cadet Soft Skills Report` | bold, size 14 |
| C2:I2 merged | `Ground School Department` | bold |
| A4 | `Please rate your observations of individual cadet from 1 to 5 using the grading system and upload in appropriate GSH shared folder for your group of subjects.` | |
| A5 | `C is the minimum required standard. Students falling in Below C Grade will be consulted by HGS and the event will be documented.` | |
| A6 | `If after consultation observations remains below C, the individual will be referred to the sponsor.` | |
| A7 | `This report will be used by HGS as part of the documentation required for the completion of Cadets Final Ground Training Report.` | |
| B8 | `Instructor: {names}`. Names = distinct `display_name` of instructors with a score set in the group, sorted case-insensitively, joined with `", "` | |
| C8 | `Subject:` | |
| D8 | Distinct subject names of the group's score sets, sorted, joined with `", "` | |
| M8 | `Date` | |
| N8:O8 merged | `export_date` as a date value | number format `DD/MM/YYYY` |
| B9:B10 merged | `Grading System` | |
| C9:E9, F9:H9, I9:K9, L9:M9, N9:O9 merged | `Excellent`, `Above standard`, `Meet standard`, `Below standard`, `Unacceptable` | fills 66FF33, C6E0B4, E2EFDA, FFC000, FF0000 |
| Row 10, same merges | `A`, `B`, `C`, `D`, `E` | same fills |
| B11; row 11, same merges | `%`; `90-100`, `80-89`, `70-79`, `60-69`, `<60` | same fills |
| B12; row 12, same merges | `Points`; 5, 4, 3, 2, 1 (numbers) | same fills |
| B13:O13 | empty | solid fill 000000 |
| Row 14 | A `No.`, B `Name`, C14:D14 `Attentiveness Engagement`, E14:F14 `Motivation Diligence Enthusiasm`, G14:H14 `Discipline Courtesy`, I14:J14 `Attire Appearance`, K14:L14 `Teamwork`, M14:N14 `Comms. Participation Interaction`, O14 `Total\nPoint` | bold, wrap text, centered |
| Rows 15 … 14+n (one per `group_results` row) | A = number, B = name; each attribute's merged pair (C:D, E:F, G:H, I:J, K:L, M:N) holds the whole-number average as an `int`; O = `=SUM(C{r}:N{r})` | averages: number format `0`, solid fill `BAND_HEX[average]`; O: `0` |
| No-data row | A, B as above; attribute cells empty; O = `no data` | |
| A14:O(14+n) | | thin border on every cell |
| Row F = 15+n, A{F}:O{F} merged | `For Additional comments specific to an individual cadet refer to next page.` | |
| Page break | `ws.row_breaks.append(Break(id=F))` | |
| Row F+4 | `Additional comments, if any:` | bold |
| Rows F+5 … | One line per comment, cells A:O merged per line, wrap text. Order: cadets in results order; within a cadet, sorted by instructor display name then subject name. Text exactly `{cadet name} — {instructor display_name} ({subject name}): {comment}`. Only active cadets, only comments non-empty after strip | |
| Row F+5 when there are no comments | `None.` | |

- Page setup: `orientation="landscape"`, `paperSize=9` (A4). Margins left/right 0.25, top/bottom 0.75, header/footer 0.3.
- The logo is not included (D16).

**Tests** (`scoring/tests/test_export_builder.py`): build with fixed data and inspect the workbook.
- `test_sheet_title_is_group_number`.
- `test_header_texts_and_course`.
- `test_instruction_text_exact`.
- `test_instructor_and_subject_header_lists`.
- `test_date_cell_value_and_format`.
- `test_grading_key_values_and_fills`.
- `test_table_header_row_and_merges`.
- `test_cadet_rows_values_fills_and_sum_formula`.
- `test_no_data_row`.
- `test_inactive_cadets_excluded`.
- `test_comments_section_format_and_order`.
- `test_no_comments_writes_none`.
- `test_footer_row_and_page_break_position`.
- `test_workbook_saves_and_reloads` (save to `BytesIO`, `load_workbook` succeeds).

**Test command**: `python manage.py test scoring.tests.test_export_builder`

**Done**: All tests pass. Manually: open a generated file in Excel or LibreOffice and compare it with the template image layout.

---

### [ ] 24. Export download

**Files**
- Change `scoring/views.py`, `scoring/urls.py`, `roster/templates/roster/group_detail.html` (admin button "Export report").
- Create `scoring/tests/test_export_view.py`.

**Behaviour**
- `groups/<str:number>/export/` → `export` (`admin_required`, GET). Works for any group status.
- Builds the workbook with `export_date = timezone.localdate()` and saves it to `BytesIO`.
- The response has content type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and `Content-Disposition: attachment; filename="Cadet_Soft_Skills_{number}_{YYYY-MM-DD}.xlsx"`.
- Logs `EXPORT_DOWNLOADED` with details `{"filename"}` and `group_number`.

**Tests** (`scoring/tests/test_export_view.py`)
- `test_instructor_forbidden`.
- `test_admin_downloads_valid_xlsx_with_filename`.
- `test_export_logged`.
- `test_export_allowed_for_locked_and_archived`.

**Test command**: `python manage.py test scoring.tests.test_export_view`

**Done**: All tests pass.

---

### [ ] 25. Audit log viewer

**Files**
- Create `audit/views.py`, `audit/urls.py`, `audit/templates/audit/event_list.html`.
- Change `config/urls.py` (`path("audit/", include("audit.urls"))`), `templates/base.html` (nav `Audit log` for admins).
- Create `audit/tests/test_viewer.py`.

**Behaviour**
- `audit/` → `event_list` (`admin_required`, `app_name = "audit"`).
- GET filters: `action` (select: "All" plus `ACTION_CHOICES`) and `group` (text, exact match after upper-case).
- Paginated with `Paginator(qs, 50)` and a `page` param, newest first. Previous/Next links keep the filters.
- Columns:
  - When: local time, `Y-m-d H:i:s`
  - Who: `actor_label`
  - Action
  - Group
  - Summary
  - Details: `json.dumps(details, ensure_ascii=False, sort_keys=True)` in `<code>`
- No edit or delete controls.

**Tests** (`audit/tests/test_viewer.py`)
- `test_instructor_forbidden`.
- `test_lists_newest_first`.
- `test_filter_by_action`.
- `test_filter_by_group`.
- `test_pagination_50_per_page`.

**Test command**: `python manage.py test audit.tests.test_viewer`

**Done**: All tests pass.

---

### [ ] 26. Demo data command and README

**Files**
- Create `roster/management/__init__.py`, `roster/management/commands/__init__.py`, `roster/management/commands/seed_demo.py`.
- Change `README.md`.
- Create `roster/tests/test_seed_demo.py`.

**Behaviour**
- `python manage.py seed_demo`:
  - If any `Group` exists → `CommandError("Database already has groups; seed_demo only runs on an empty database.")`.
  - Otherwise, in one transaction:
    - Create subjects `Air Law`, `Meteorology`, `Navigation`.
    - Load `samples/sample_roster.xlsx` through `roster.services` (`read_sheet`, `parse_rows` with Course Group / Full Name / Cadet ID, then the same apply function used by Slice 13, with course number `216.18` and actor None / `actor_label="seed_demo"`).
  - Print `Seeded 3 subjects, 3 groups, 44 cadets.`
  - It doesn't create users or scores.
- `README.md` sections:
  1. What it is (one sentence)
  2. Setup (venv, `pip install -r requirements.txt`, `migrate`)
  3. Create the first admin (`createadmin`)
  4. Run (`runserver`, localhost only)
  5. Demo data (`seed_demo`)
  6. Tests (`python manage.py test`)
  7. Configuration table of every env var: `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_TIME_ZONE`, `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `LOGIN_MODE`, `MFA_REQUIRED`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_REDIRECT_URI`, `ROSTER_MAX_UPLOAD_BYTES`, each with its default and meaning
  8. "Fake data only" warning

**Tests** (`roster/tests/test_seed_demo.py`)
- `test_seeds_subjects_groups_cadets`.
- `test_refuses_when_groups_exist`.

**Test command**: `python manage.py test roster.tests.test_seed_demo`

**Done**: All tests pass. Full manual walk-through on a fresh database:
1. `migrate`, `createadmin`, `seed_demo`, `runserver`.
2. Sign in, set a password, (MFA if on).
3. Create an instructor, then sign in as them and score C216 for two subjects.
4. As admin, score C216 too, view results, lock the group, export, open the `.xlsx`.
5. View the audit log.

---

## Requirement coverage

| REQUIREMENTS.md section | Slices |
|---|---|
| 1 Platform / PoC | 1, 3, 26 |
| 2 Authentication | 3, 4, 5, 6, 7, 8 |
| 3 Roles and permissions | 5, 7, 15, 17–25 |
| 4 Roster upload | 10, 11, 12, 13 |
| 5 Groups | 10, 17, 18 |
| 6 Subjects | 9, 17 |
| 7 Scoring | 14, 15, 16, 18 |
| 8 Results | 21, 22 |
| 9 Export | 23, 24 |
| 10 Lifecycle | 7, 18, 19, 21 |
| 11 Audit log | 2, and every slice that changes data; viewer in 25 |

Not covered until hosting is decided: `SECURE_PROXY_SSL_HEADER`, PostgreSQL driver (`psycopg`), production web server.
