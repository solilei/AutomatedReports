from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from accounts.decorators import admin_required
from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent

NEW_PASSWORD = "a-brand-new-passphrase"


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class AccessGateTests(TestCase):
    def test_unapproved_user_redirected_to_pending(self):
        make_user(is_approved=False)
        self.client.login(username="inst", password="correct-horse-battery")
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/pending/", fetch_redirect_response=False)

    def test_pending_page_accessible_to_unapproved(self):
        make_user(is_approved=False)
        self.client.login(username="inst", password="correct-horse-battery")
        response = self.client.get("/accounts/pending/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your account is waiting for an administrator to approve it.")
        self.assertContains(response, "Sign out")

    def test_approved_user_not_redirected_from_pending(self):
        make_user()
        self.client.login(username="inst", password="correct-horse-battery")
        response = self.client.get("/accounts/pending/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_must_change_password_redirects_to_password_set(self):
        make_user(must_change_password=True)
        self.client.login(username="inst", password="correct-horse-battery")
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/password/set/", fetch_redirect_response=False)

    def test_password_set_clears_flag_and_keeps_session(self):
        user = make_user(must_change_password=True)
        self.client.login(username="inst", password="correct-horse-battery")
        response = self.client.post(
            "/accounts/password/set/", {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_password_set_enforces_min_length_12(self):
        user = make_user(must_change_password=True)
        self.client.login(username="inst", password="correct-horse-battery")
        response = self.client.post(
            "/accounts/password/set/", {"new_password1": "short-pw-1", "new_password2": "short-pw-1"}
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.check_password("correct-horse-battery"))

    def test_password_set_writes_audit_event(self):
        make_user(must_change_password=True)
        self.client.login(username="inst", password="correct-horse-battery")
        self.client.post("/accounts/password/set/", {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        event = AuditEvent.objects.get(action=actions.ACCOUNT_PASSWORD_SET)
        self.assertEqual(event.summary, "inst set their password")
        self.assertNotIn(NEW_PASSWORD, str(event.details))

    def test_password_set_get_redirects_home_when_flag_clear(self):
        make_user()
        self.client.login(username="inst", password="correct-horse-battery")
        response = self.client.get("/accounts/password/set/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)


class AdminRequiredTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        @admin_required
        def view(request):
            return HttpResponse("ok")

        self.view = view

    def test_admin_required_403_for_instructor(self):
        request = self.factory.get("/x/")
        request.user = make_user()
        with self.assertRaises(PermissionDenied):
            self.view(request)

    def test_admin_required_allows_admin(self):
        request = self.factory.get("/x/")
        request.user = make_user("boss", role="admin")
        self.assertEqual(self.view(request).status_code, 200)
