# Handoff
## Done
- CLAUDE.md, REQUIREMENTS.md (defaults confirmed), PLAN.md (26 slices).
- Slice 1 (scaffold, settings, custom user model) committed and pushed at `5787b17`. 6 tests pass.
- Slice 2 (audit log model and `log()` helper) committed and pushed at `04bd209`. 8 audit tests pass, 14 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 3 (base layout, local login/logout, `LOGIN_MODE`, session rules) committed and pushed at `9a43e6f`. 16 new tests; 30 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 4 (`createadmin` management command) committed and pushed at `c4ee082`. 4 new tests; 34 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 5 (access gate, `admin_required`, pending and password-set pages) committed and pushed at `d6cc0c5`. 10 new tests; 44 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 6 (authenticator-app MFA: `accounts/mfa.py`, `mfa_setup`, `mfa_verify`, login branch) committed and pushed at `07a9dfd`. 11 new tests; 55 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- `.venv` created locally (git-ignored); run `source .venv/bin/activate` first.
## Next
- Slice 7 (account management, admin) in PLAN.md, only when the user says to start. Don't write code until then.
## Open problems
- Real roster: is there a cadet ID column? Retention period, hosting, Postgres host, HTTPS, Entra app registration, data-protection sign-off.
- The login page's Microsoft button links to `/accounts/microsoft/login/`, which 404s until Slice 8.
- Slice 6 manual check (`createadmin`, sign in, scan the QR in a real authenticator app, forced password set) has not been done (tests only).
- MFA applies to every user who signs in through `login_view` (local form). Microsoft users (Slice 8) must not pass through it.
- A TOTP code can be reused within its validity window; there is no replay protection.
- `AccessGateMiddleware` exempts `accounts:microsoft_login` and `microsoft_callback`, which don't exist yet (Slice 8); no test covers those entries. `mfa_setup` and `mfa_verify` now exist and are exercised by the MFA tests.
- Slice 5 manual check (`runserver`, unapproved and forced-password-change redirects) has not been done (tests only).
- Nothing links to the admin-only role decorator yet; `admin_required` is tested with `RequestFactory` only.
- Manual check of `createadmin` against the real `db.sqlite3` has not been done (tests only).
- `createadmin` prints the temporary password to stdout; it's never logged, but it will appear in terminal scrollback.
- Manual check from Slice 3's "Done" line (`runserver`, `/` redirects to login) has not been done.
- `test_allowed_hosts_default_localhost_only` reads `config.settings` directly, because the test runner adds `"testserver"` to `django.conf.settings`. PLAN.md's wording would never pass.
- Commit `04bd209` message reads `Slice 2: Audit log model and  helper` (backticks around `log()` were eaten by the shell). Already pushed; amend only if the user asks.
- `AuditEvent` immutability is enforced in `save()`/`delete()` only. Queryset `.update()` and `.delete()` bypass it, and the ordering test uses `.update()` on purpose.
## Decisions made
- Django 5.2 LTS + openpyxl, pyotp, segno, msal (approved). PLAN.md D1–D18 accepted.
- Averages rounded half up to whole numbers (2.5 → C). Total = sum of six (6–30).
- One course number per upload, typed by the admin each time (box starts empty).
- `.xlsx` only, 5 MB max. The last admin can't be demoted or deactivated.
- Slice 1, 2, 3, 4, 5 and 6 tests are frozen: don't modify test files unless the user asks.
