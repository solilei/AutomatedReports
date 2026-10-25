import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from audit import service as audit
from audit.actions import ACCOUNT_CREATED

User = get_user_model()


class Command(BaseCommand):
    help = "Create the first admin account with a temporary password."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--full-name", required=True)

    def handle(self, *args, **options):
        username = options["username"]
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists.")

        password = secrets.token_urlsafe(12)
        user = User(
            username=username,
            full_name=options["full_name"],
            role=User.Role.ADMIN,
            auth_source=User.Source.LOCAL,
            is_approved=True,
            must_change_password=True,
            is_staff=False,
            is_superuser=False,
        )
        user.set_password(password)
        user.save()

        audit.log(
            None,
            ACCOUNT_CREATED,
            f"Admin '{username}' created from command line",
            actor_label="command line",
            details={"username": username, "role": "admin"},
        )
        self.stdout.write(f"Created admin '{username}'.")
        self.stdout.write(f"Temporary password (shown once): {password}")
