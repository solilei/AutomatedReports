from django.core.management.base import BaseCommand

from roster.services import discard_stale_uploads


class Command(BaseCommand):
    help = "Discard roster uploads left unfinished for over 24 hours, deleting their stored files."

    def handle(self, *args, **options):
        count = discard_stale_uploads()
        self.stdout.write(f"Discarded {count} stale upload(s).")
