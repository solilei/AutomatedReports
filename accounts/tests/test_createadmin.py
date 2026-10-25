from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from audit.actions import ACCOUNT_CREATED
from audit.models import AuditEvent

User = get_user_model()


def run_createadmin(username="boss", full_name="Boss Person"):
    out = StringIO()
    call_command("createadmin", username=username, full_name=full_name, stdout=out)
    return out.getvalue()


def parse_password(output):
    return output.splitlines()[1].split(": ", 1)[1]


class CreateAdminTests(TestCase):
    def test_creates_approved_admin_needing_password_change(self):
        run_createadmin()
        user = User.objects.get(username="boss")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertEqual(user.auth_source, User.Source.LOCAL)
        self.assertEqual(user.full_name, "Boss Person")
        self.assertTrue(user.is_approved)
        self.assertTrue(user.must_change_password)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_printed_password_works(self):
        output = run_createadmin()
        lines = output.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "Created admin 'boss'.")
        self.assertTrue(lines[1].startswith("Temporary password (shown once): "))
        user = User.objects.get(username="boss")
        self.assertTrue(user.check_password(parse_password(output)))

    def test_duplicate_username_raises_command_error(self):
        User.objects.create_user("boss", password="x")
        with self.assertRaisesMessage(CommandError, "User 'boss' already exists."):
            run_createadmin()

    def test_audit_event_written_without_password(self):
        output = run_createadmin()
        password = parse_password(output)
        event = AuditEvent.objects.get()
        self.assertEqual(event.action, ACCOUNT_CREATED)
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_label, "command line")
        self.assertEqual(event.summary, "Admin 'boss' created from command line")
        self.assertEqual(event.details, {"username": "boss", "role": "admin"})
        self.assertNotIn(password, event.summary)
        self.assertNotIn(password, str(event.details))
