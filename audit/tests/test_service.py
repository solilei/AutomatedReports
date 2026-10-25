from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from audit import actions
from audit.models import AuditEvent
from audit.service import log


class AuditServiceTests(TestCase):
    def test_log_creates_event_with_actor_label(self):
        user = User.objects.create_user(username="u1", password="x")
        event = log(
            user,
            actions.GROUP_LOCKED,
            "Locked group",
            group_number="216.18",
            details={"a": 1},
        )
        event.refresh_from_db()
        self.assertEqual(event.actor, user)
        self.assertEqual(event.actor_label, "u1")
        self.assertEqual(event.action, "group.locked")
        self.assertEqual(event.group_number, "216.18")
        self.assertEqual(event.summary, "Locked group")
        self.assertEqual(event.details, {"a": 1})

    def test_log_without_actor_uses_system_label(self):
        event = log(None, actions.EXPORT_DOWNLOADED, "Exported")
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_label, "system")
        self.assertEqual(event.group_number, "")
        self.assertEqual(event.details, {})

    def test_log_with_explicit_actor_label(self):
        event = log(None, actions.ACCOUNT_CREATED, "Created", actor_label="command line")
        self.assertEqual(event.actor_label, "command line")

    def test_unknown_action_raises(self):
        with self.assertRaises(ValueError):
            log(None, "not.an.action", "x")
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_event_cannot_be_updated(self):
        event = log(None, actions.SCORE_CHANGED, "x")
        event.summary = "changed"
        with self.assertRaisesMessage(ValueError, "Audit events are immutable"):
            event.save()
        self.assertEqual(AuditEvent.objects.get(pk=event.pk).summary, "x")

    def test_event_cannot_be_deleted(self):
        event = log(None, actions.SCORE_CHANGED, "x")
        with self.assertRaisesMessage(ValueError, "Audit events cannot be deleted"):
            event.delete()
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_events_ordered_newest_first(self):
        first = log(None, actions.SCORE_CHANGED, "first")
        second = log(None, actions.SCORE_CHANGED, "second")
        third = log(None, actions.SCORE_CHANGED, "third")
        AuditEvent.objects.filter(pk=first.pk).update(
            timestamp=timezone.now() - timedelta(days=1)
        )
        self.assertEqual(
            list(AuditEvent.objects.values_list("summary", flat=True)),
            ["third", "second", "first"],
        )

    def test_summary_truncated_to_500(self):
        event = log(None, actions.COMMENT_CHANGED, "x" * 600)
        self.assertEqual(len(event.summary), 500)
        self.assertEqual(len(AuditEvent.objects.get(pk=event.pk).summary), 500)
