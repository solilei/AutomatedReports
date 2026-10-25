from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import User
from audit.models import AuditEvent
from roster.models import Cadet, Group
from roster.tests.helpers import make_group
from scoring.models import ScoreSet, Subject


class SeedDemoTests(TestCase):
    def test_seeds_subjects_groups_cadets(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)

        self.assertEqual(
            list(Subject.objects.order_by("name").values_list("name", flat=True)),
            ["Air Law", "Meteorology", "Navigation"],
        )
        self.assertEqual(
            list(Group.objects.order_by("number").values_list("number", flat=True)),
            ["C216", "C217", "C218"],
        )
        self.assertEqual(Cadet.objects.count(), 44)
        self.assertIn("Seeded 3 subjects, 3 groups, 44 cadets.", out.getvalue())
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(ScoreSet.objects.count(), 0)
        self.assertTrue(AuditEvent.objects.filter(actor_label="seed_demo").exists())

    def test_refuses_when_groups_exist(self):
        make_group("C999")
        with self.assertRaisesMessage(
            CommandError,
            "Database already has groups; seed_demo only runs on an empty database.",
        ):
            call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Subject.objects.count(), 0)
        self.assertEqual(Group.objects.count(), 1)
