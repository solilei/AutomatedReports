# Handoff
## Done
- CLAUDE.md, REQUIREMENTS.md (defaults confirmed), PLAN.md (26 slices).
- Slice 1 (scaffold, settings, custom user model) committed and pushed at `5787b17`. 6 tests pass.
- Slice 2 (audit log model and `log()` helper) committed and pushed at `04bd209`. 8 audit tests pass, 14 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 3 (base layout, local login/logout, `LOGIN_MODE`, session rules) committed and pushed at `9a43e6f`. 16 new tests; 30 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 4 (`createadmin` management command) committed and pushed at `c4ee082`. 4 new tests; 34 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 5 (access gate, `admin_required`, pending and password-set pages) committed and pushed at `d6cc0c5`. 10 new tests; 44 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 6 (authenticator-app MFA: `accounts/mfa.py`, `mfa_setup`, `mfa_verify`, login branch) committed and pushed at `07a9dfd`. 11 new tests; 55 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 7 (account management: `accounts/services.py`, `user_list`/`user_create`/row actions/`user_reset`, Accounts nav link) committed and pushed at `b98efff`. 16 new tests; 71 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- Slice 8 (Microsoft Entra ID sign-in: `accounts/microsoft.py`, `microsoft_login`/`microsoft_callback`, `ENTRA_*` settings, error page) committed and pushed at `5ec5e3f`. 15 new tests; 86 in the full suite; `check` and `makemigrations --check` are clean. Ticked in PLAN.md.
- `.venv` created locally (git-ignored); run `source .venv/bin/activate` first.
## Next
- Slice 9 (Subjects) in PLAN.md, only when the user says to start. Don't write code until then.
## Open problems
- Real roster: is there a cadet ID column? Retention period, hosting, Postgres host, HTTPS, Entra app registration, data-protection sign-off.
- Slice 8: the real Microsoft round trip (Entra app registration, redirect URI, sign-in, first-sign-in pending account, admin approval) has not been tried; tests mock msal. Needs the Entra app registration listed above.
- Slice 8: the Microsoft button only appears when `LOGIN_MODE` is `microsoft` or `both`; the default `local` shows no button and the routes 404.
- Slice 6 manual check (`createadmin`, sign in, scan the QR in a real authenticator app, forced password set) has not been done (tests only).
- MFA applies only to users who sign in through `login_view` (local form). Microsoft users skip it by design (covered by `test_microsoft_user_skips_local_mfa`).
- A TOTP code can be reused within its validity window; there is no replay protection.
- `AccessGateMiddleware` exempts `accounts:microsoft_login` and `microsoft_callback`; both routes now exist, but no test targets the exemption directly (only unauthenticated or approved users reach them in tests).
- Slice 5 manual check (`runserver`, unapproved and forced-password-change redirects) has not been done (tests only).
- Manual check of `createadmin` against the real `db.sqlite3` has not been done (tests only).
- `createadmin` prints the temporary password to stdout; it's never logged, but it will appear in terminal scrollback.
- Manual check from Slice 3's "Done" line (`runserver`, `/` redirects to login) has not been done.
- `test_allowed_hosts_default_localhost_only` reads `config.settings` directly, because the test runner adds `"testserver"` to `django.conf.settings`. PLAN.md's wording would never pass.
- Commit `04bd209` message reads `Slice 2: Audit log model and  helper` (backticks around `log()` were eaten by the shell). Already pushed; amend only if the user asks.
- `AuditEvent` immutability is enforced in `save()`/`delete()` only. Queryset `.update()` and `.delete()` bypass it, and the ordering test uses `.update()` on purpose.
- Slice 7: the "last admin" deactivate message is unreachable from the UI (only an admin can act, so the last admin is always the actor and hits the self-check first). The rule is covered via `services.is_last_admin`.
- Slice 7 manual check (`runserver`, create an account, sign in with the temp password) has not been done (tests only).
- Slice 7: temp passwords appear once on the create/reset page (`Cache-Control: no-store`) and are never logged; they stay in browser history/scrollback of that page view.
- Slice 7: `user_reset` returns 403 for non-local users; Microsoft accounts rely on that.
- Slice 8: a Microsoft sign-in whose username matches an existing local account gets a 409; there is no account linking. A callback replay fails because the `entra_flow` session value is popped on first use.
- Slice 8: `test_microsoft` settings tests reload `config.settings` (module only, not `django.conf.settings`) and reload it again afterwards.
## Decisions made
- Django 5.2 LTS + openpyxl, pyotp, segno, msal (approved). PLAN.md D1–D18 accepted.
- Averages rounded half up to whole numbers (2.5 → C). Total = sum of six (6–30).
- One course number per upload, typed by the admin each time (box starts empty).
- `.xlsx` only, 5 MB max. The last admin can't be demoted or deactivated.
- Slice 1, 2, 3, 4, 5, 6, 7 and 8 tests are frozen: don't modify test files unless the user asks.
