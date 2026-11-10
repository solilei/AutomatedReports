from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from audit import service as audit
from audit.actions import ACCOUNT_ADMIN_TRANSFERRED

User = get_user_model()


class Command(BaseCommand):
    help = "Hand the admin role to another account. There is only ever one admin."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Username of the new admin.")

    def handle(self, *args, **options):
        username = options["to"]
        with transaction.atomic():
            target = User.objects.select_for_update().filter(username=username).first()
            if target is None:
                raise CommandError(f"User '{username}' does not exist.")
            if not target.is_approved:
                raise CommandError(f"User '{username}' is not approved.")
            if not target.is_active:
                raise CommandError(f"User '{username}' is deactivated.")
            if target.role == User.Role.ADMIN:
                raise CommandError(f"User '{username}' is already the admin.")

            old_admins = list(User.objects.select_for_update().filter(role=User.Role.ADMIN))
            old_names = ", ".join(u.username for u in old_admins) or "nobody"
            User.objects.filter(pk__in=[u.pk for u in old_admins]).update(role=User.Role.INSTRUCTOR)
            target.role = User.Role.ADMIN
            target.save(update_fields=["role"])

            audit.log(
                None,
                ACCOUNT_ADMIN_TRANSFERRED,
                f"Admin role moved from {old_names} to {username}",
                actor_label="command line",
                details={"from": old_names, "to": username},
            )
        self.stdout.write(f"Admin role moved from {old_names} to {username}.")
