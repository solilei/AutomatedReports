from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent

PASSWORD = "correct-horse-battery"


def url(name, user=None):
    return reverse(f"accounts:{name}", args=[user.pk] if user else [])


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def create_via_form(self, username="newbie", role="instructor", full_name="New Bie"):
        return self.client.post(
            url("user_create"), {"username": username, "full_name": full_name, "role": role}
        )

    def test_instructor_gets_403_on_every_manage_url(self):
        instructor = make_user("inst")
        target = make_user("other")
        self.client.force_login(instructor)
        for name in ("user_list", "user_create"):
            self.assertEqual(self.client.get(url(name)).status_code, 403, name)
        for name in ("user_approve", "user_promote", "user_demote", "user_deactivate", "user_reactivate", "user_reset"):
            self.assertEqual(self.client.post(url(name, target)).status_code, 403, name)

    def test_create_local_user_shows_temp_password_once_and_sets_flags(self):
        response = self.create_via_form()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        user = User.objects.get(username="newbie")
        self.assertEqual(user.auth_source, User.Source.LOCAL)
        self.assertTrue(user.is_approved)
        self.assertTrue(user.must_change_password)
        self.assertEqual(user.role, User.Role.INSTRUCTOR)
        self.assertEqual(user.full_name, "New Bie")
        password = response.context["password"]
        self.assertTrue(user.check_password(password))
        self.assertContains(response, f"Temporary password for newbie: {password}")
        self.assertContains(
            response, "This password is shown once. Give it to the user; they must change it at first sign-in."
        )
        listing = self.client.get(url("user_list"))
        self.assertNotContains(listing, password)

    def test_created_user_can_login_with_temp_password_and_is_forced_to_set_password(self):
        password = self.create_via_form().context["password"]
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username": "newbie", "password": password})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        response = self.client.get("/")
        self.assertRedirects(response, reverse("accounts:password_set"), fetch_redirect_response=False)

    def test_create_duplicate_username_rejected(self):
        make_user("newbie")
        response = self.create_via_form()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="newbie").count(), 1)
        self.assertTrue(response.context["form"].errors["username"])

    def test_approve_pending_user(self):
        pending = make_user("pend", is_approved=False)
        response = self.client.post(url("user_approve", pending))
        self.assertRedirects(response, url("user_list"), fetch_redirect_response=False)
        pending.refresh_from_db()
        self.assertTrue(pending.is_approved)

    def test_promote_requires_approval(self):
        pending = make_user("pend", is_approved=False)
        response = self.client.post(url("user_promote", pending), follow=True)
        pending.refresh_from_db()
        self.assertEqual(pending.role, User.Role.INSTRUCTOR)
        self.assertContains(response, "Approve the account first.")

    def test_promote_and_demote(self):
        target = make_user("target")
        self.client.post(url("user_promote", target))
        target.refresh_from_db()
        self.assertEqual(target.role, User.Role.ADMIN)
        self.client.post(url("user_demote", target))
        target.refresh_from_db()
        self.assertEqual(target.role, User.Role.INSTRUCTOR)

    def test_cannot_demote_last_admin(self):
        response = self.client.post(url("user_demote", self.admin), follow=True)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)
        self.assertContains(response, "Cannot demote the last remaining admin.")

    def test_cannot_deactivate_last_admin(self):
        # Only an admin can act, so the last admin can only target themselves; the self check fires first.
        # The last-admin rule itself lives in services.is_last_admin.
        from accounts import services

        make_user("unapproved_admin", role="admin", is_approved=False)
        self.assertTrue(services.is_last_admin(self.admin))
        self.client.post(url("user_deactivate", self.admin))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        second = make_user("second", role="admin")
        self.assertFalse(services.is_last_admin(self.admin))
        self.assertEqual(services.active_admin_count(), 2)
        self.assertFalse(services.is_last_admin(second))

    def test_cannot_deactivate_self(self):
        make_user("second", role="admin")
        response = self.client.post(url("user_deactivate", self.admin), follow=True)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertContains(response, "You cannot deactivate your own account.")

    def test_deactivated_user_cannot_login(self):
        target = make_user("target")
        self.client.post(url("user_deactivate", target))
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username": "target", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_deactivated_user_existing_session_is_ended(self):
        target = make_user("target")
        other = self.client_class()
        other.force_login(target)
        self.assertEqual(other.get("/").status_code, 200)
        self.client.post(url("user_deactivate", target))
        response = other.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("accounts:login")))

    def test_reset_clears_mfa_and_sets_new_temp_password(self):
        target = make_user("target", totp_secret="ABCDEFGHIJKLMNOP", totp_confirmed=True)
        response = self.client.post(url("user_reset", target))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        target.refresh_from_db()
        password = response.context["password"]
        self.assertTrue(target.check_password(password))
        self.assertFalse(target.check_password(PASSWORD))
        self.assertTrue(target.must_change_password)
        self.assertEqual(target.totp_secret, "")
        self.assertFalse(target.totp_confirmed)
        self.assertContains(response, password)

    def test_reset_not_allowed_for_microsoft_user(self):
        target = make_user("msuser", auth_source=User.Source.MICROSOFT)
        response = self.client.post(url("user_reset", target))
        self.assertEqual(response.status_code, 403)

    def test_each_action_writes_expected_audit_action(self):
        self.create_via_form()
        newbie = User.objects.get(username="newbie")
        pending = make_user("pend", is_approved=False)
        self.client.post(url("user_approve", pending))
        self.client.post(url("user_promote", newbie))
        self.client.post(url("user_demote", newbie))
        self.client.post(url("user_deactivate", newbie))
        self.client.post(url("user_reactivate", newbie))
        self.client.post(url("user_reset", newbie))
        logged = list(AuditEvent.objects.order_by("id").values_list("action", flat=True))
        self.assertEqual(
            logged,
            [
                actions.ACCOUNT_CREATED,
                actions.ACCOUNT_APPROVED,
                actions.ACCOUNT_PROMOTED,
                actions.ACCOUNT_DEMOTED,
                actions.ACCOUNT_DEACTIVATED,
                actions.ACCOUNT_REACTIVATED,
                actions.ACCOUNT_RESET,
            ],
        )
        created = AuditEvent.objects.get(action=actions.ACCOUNT_CREATED)
        self.assertEqual(created.details, {"username": "newbie", "role": "instructor"})
        self.assertEqual(created.actor, self.admin)
        for event in AuditEvent.objects.all():
            self.assertNotIn(PASSWORD, event.summary + str(event.details))

    def test_get_on_action_url_returns_405(self):
        target = make_user("target")
        for name in ("user_approve", "user_promote", "user_demote", "user_deactivate", "user_reactivate", "user_reset"):
            self.assertEqual(self.client.get(url(name, target)).status_code, 405, name)
