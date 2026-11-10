from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import secrets

from accounts.models import User
from roster.models import Cadet, Group
from roster.services import apply_upload, check_groups, parse_rows, read_sheet
from scoring.assignments import set_assignments
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.models import Programme, Subject
from scoring.programmes import ATPL_NAME
from scoring.services import save_score_set

INSTRUCTORS = [
    ("alex", "Alex Tan", ["Meteorology", "Air Law"]),
    ("sam", "Sam Lee", ["Meteorology", "General Navigation"]),
]
# (username, subject) pairs that get a full score set in C216. sam's General Navigation stays missing.
SCORED = [("alex", "Meteorology"), ("alex", "Air Law"), ("sam", "Meteorology")]
SAMPLE_FILES = ["sample_roster_C216.xlsx", "sample_roster_C217.xlsx", "sample_roster_C218.xlsx"]


class _DemoUpload:
    """Stands in for a RosterUpload: the apply step needs one, but the demo has no uploader."""

    pk = None
    status = "parsed"
    file_content = b""

    def __init__(self, filename, parsed, programme):
        self.original_filename = filename
        self.programme = programme
        self.parsed = parsed

    def save(self):
        pass


class Command(BaseCommand):
    help = "Load demo subjects and the sample rosters into an empty database."

    def handle(self, *args, **options):
        if Group.objects.exists():
            raise CommandError("Database already has groups; seed_demo only runs on an empty database.")
        programme = Programme.objects.filter(name=ATPL_NAME).first()
        if programme is None:
            raise CommandError("The ATPL programme is missing. Run migrate first.")

        passwords = {}
        with transaction.atomic():
            for filename in SAMPLE_FILES:
                self._load(filename, programme)
            users = {}
            for username, full_name, subject_names in INSTRUCTORS:
                if User.objects.filter(username=username).exists():
                    raise CommandError(f"User '{username}' already exists.")
                passwords[username] = secrets.token_urlsafe(12)
                user = User(
                    username=username,
                    full_name=full_name,
                    role=User.Role.INSTRUCTOR,
                    auth_source=User.Source.LOCAL,
                    is_approved=True,
                    must_change_password=True,
                )
                user.set_password(passwords[username])
                user.save()
                users[username] = user
                subjects = Subject.objects.filter(programme=programme, name__in=subject_names)
                set_assignments(None, user, list(subjects))
            group = Group.objects.get(number="C216")
            for username, subject_name in SCORED:
                subject = Subject.objects.get(programme=programme, name=subject_name)
                data = {
                    cadet.pk: {"scores": {f: 4 for f in ATTRIBUTE_FIELDS}, "comment": ""}
                    for cadet in group.cadets.filter(is_active=True)
                }
                save_score_set(users[username], subject, group, data)

        for username, password in passwords.items():
            self.stdout.write(f"Created instructor '{username}'. Temporary password (shown once): {password}")
        self.stdout.write(
            f"Seeded {Group.objects.count()} groups, {Cadet.objects.count()} cadets, "
            f"{len(INSTRUCTORS)} instructors, {len(SCORED)} score sets."
        )

    def _load(self, filename, programme):
        number = filename.split("_")[-1].split(".")[0]
        content = (settings.BASE_DIR / "samples" / filename).read_bytes()
        headers, rows = read_sheet(content)
        result = parse_rows(rows, number, headers.index("Full Name"), headers.index("Cadet ID"))
        errors = result.errors or check_groups(list(result.groups), True, programme=programme)
        if errors:
            raise CommandError(f"{filename}: {' '.join(errors)}")
        apply_upload(
            _DemoUpload(filename, {"id_mode": True, "groups": result.groups}, programme),
            None,
            actor_label="seed_demo",
        )
