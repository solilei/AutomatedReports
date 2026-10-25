# Handoff
## Done
- CLAUDE.md, REQUIREMENTS.md (defaults confirmed), PLAN.md (26 slices).
- Slice 1 (scaffold, settings, custom user model) committed and pushed at `5787b17`. 6 tests pass; `check`, `makemigrations --check` and `migrate` are clean; runserver binds to 127.0.0.1:8000.
- `.venv` created locally (git-ignored); run `source .venv/bin/activate` first.
## Next
- Slice 2 (audit log model and `log()` helper) in PLAN.md, only when the user says to start. Don't write code until then.
## Open problems
- Real roster: is there a cadet ID column? Retention period, hosting, Postgres host, HTTPS, Entra app registration, data-protection sign-off.
- `python manage.py runserver` currently serves Django's default welcome page, since `urlpatterns` is empty until Slice 3.
## Decisions made
- Django 5.2 LTS + openpyxl, pyotp, segno, msal (approved). PLAN.md D1–D18 accepted.
- Averages rounded half up to whole numbers (2.5 → C). Total = sum of six (6–30).
- One course number per upload, typed by the admin each time (box starts empty).
- `.xlsx` only, 5 MB max. The last admin can't be demoted or deactivated.
- Slice 1 tests are frozen: don't modify test files unless the user asks.
