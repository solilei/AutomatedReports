# CLAUDE.md

Django web app for scoring cadets on six soft-skill attributes and exporting the Cadet Soft Skills Report. Spec: `REQUIREMENTS.md`. Export template: `report.md`. Sample roster: `samples/`.

## Stack
- Python 3.14, Django
- SQLite for the proof of concept; keep the database layer PostgreSQL-compatible
- Fake cadet names only; no real cadet data

## Run and test
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver        # binds to 127.0.0.1 only; never 0.0.0.0
python manage.py test
```

## Rules
- Ask before adding any dependency.
- Never modify test files unless I ask.
- Never commit or push unless I ask.
- Never commit `.env` files or secrets.

## Reply style
- Keep replies short.
- Explain any new concept in 1-2 sentences.
- End each reply with a numbered list of next steps or questions.
