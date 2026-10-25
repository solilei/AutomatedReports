from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from roster.models import Cadet, Group
from roster.services import apply_upload, check_groups, parse_rows, read_sheet
from scoring.models import Subject

SUBJECTS = ["Air Law", "Meteorology", "Navigation"]
SAMPLE_FILES = ["sample_roster_C216.xlsx", "sample_roster_C217.xlsx", "sample_roster_C218.xlsx"]


class _DemoUpload:
    """Stands in for a RosterUpload: the apply step needs one, but the demo has no uploader."""

    pk = None
    status = "parsed"
    file_content = b""

    def __init__(self, filename, parsed):
        self.original_filename = filename
        self.parsed = parsed

    def save(self):
        pass


class Command(BaseCommand):
    help = "Load demo subjects and the sample rosters into an empty database."

    def handle(self, *args, **options):
        if Group.objects.exists():
            raise CommandError("Database already has groups; seed_demo only runs on an empty database.")

        with transaction.atomic():
            for name in SUBJECTS:
                Subject.objects.get_or_create(name=name)
            for filename in SAMPLE_FILES:
                self._load(filename)

        self.stdout.write(
            f"Seeded {len(SUBJECTS)} subjects, {Group.objects.count()} groups, "
            f"{Cadet.objects.count()} cadets."
        )

    def _load(self, filename):
        number = filename.split("_")[-1].split(".")[0]
        content = (settings.BASE_DIR / "samples" / filename).read_bytes()
        headers, rows = read_sheet(content)
        result = parse_rows(rows, number, headers.index("Full Name"), headers.index("Cadet ID"))
        errors = result.errors or check_groups(list(result.groups), True)
        if errors:
            raise CommandError(f"{filename}: {' '.join(errors)}")
        apply_upload(
            _DemoUpload(filename, {"id_mode": True, "groups": result.groups}),
            None,
            actor_label="seed_demo",
        )
