# AutomatedReports

A Django web app where instructors score cadets on six soft-skill attributes and an admin exports the Cadet Soft Skills Report.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

## Create the first admin

```bash
python manage.py createadmin --username admin --full-name "Admin Name"
```

It prints a temporary password once. You set a new one at first sign-in.

## Run

```bash
python manage.py runserver        # 127.0.0.1 only; never bind 0.0.0.0
```

## Demo data

```bash
python manage.py seed_demo
```

Loads the subjects Air Law, Meteorology and Navigation and the sample rosters in `samples/` (groups C216, C217, C218; 44 cadets). It creates no users or scores and only runs on a database with no groups.

## Tests

```bash
python manage.py test
```

## Configuration

All settings are environment variables.

| Variable | Default | Meaning |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Debug mode. Accepts `1`, `true`, `yes`, `on`. When off, `DJANGO_SECRET_KEY` is required and `MFA_REQUIRED` is forced on. |
| `DJANGO_SECRET_KEY` | insecure dev key (debug only) | Django secret key. |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated host names the app serves. |
| `DJANGO_TIME_ZONE` | `UTC` | Display time zone. |
| `DB_ENGINE` | `sqlite` | `sqlite` or `postgresql`. |
| `DB_NAME` | none | PostgreSQL database name. |
| `DB_USER` | none | PostgreSQL user. |
| `DB_PASSWORD` | none | PostgreSQL password. |
| `DB_HOST` | none | PostgreSQL host. |
| `DB_PORT` | `5432` | PostgreSQL port. |
| `LOGIN_MODE` | `local` | `local`, `microsoft` or `both`. |
| `MFA_REQUIRED` | `True` | Require an authenticator-app code for local sign-in. |
| `ENTRA_TENANT_ID` | empty | Microsoft Entra tenant ID. Required when `LOGIN_MODE` is `microsoft` or `both`. |
| `ENTRA_CLIENT_ID` | empty | Entra app client ID. Same requirement. |
| `ENTRA_CLIENT_SECRET` | empty | Entra app client secret. Same requirement. |
| `ENTRA_REDIRECT_URI` | empty | Entra sign-in redirect URI. Same requirement. |
| `ROSTER_MAX_UPLOAD_BYTES` | `5242880` (5 MB) | Largest roster `.xlsx` accepted. |

## Fake data only

Use fake cadet names only. Never load real cadet data into this proof of concept.
