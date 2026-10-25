import importlib
import os
import time
from unittest import mock

import pyotp
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from config import settings as project_settings

PASSWORD = "correct-horse-battery"


@override_settings(MFA_REQUIRED=True, LOGIN_MODE="local")
class MfaTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def post_login(self, **extra):
        data = {"username": "inst", "password": PASSWORD, **extra}
        return self.client.post("/accounts/login/", data)

    def is_logged_in(self):
        return "_auth_user_id" in self.client.session

    def enroll(self):
        secret = pyotp.random_base32()
        self.user.totp_secret = secret
        self.user.totp_confirmed = True
        self.user.save()
        return secret

    def test_login_without_mfa_enrolled_goes_to_setup_and_is_not_logged_in(self):
        response = self.post_login()
        self.assertRedirects(response, "/accounts/mfa/setup/", fetch_redirect_response=False)
        self.assertFalse(self.is_logged_in())
        self.assertEqual(self.client.session["mfa_user_id"], self.user.pk)

    def test_setup_with_valid_code_enrolls_and_logs_in(self):
        self.post_login()
        response = self.client.get("/accounts/mfa/setup/")
        self.assertEqual(response.status_code, 200)
        secret = self.client.session["mfa_new_secret"]
        self.assertContains(response, secret)
        self.assertContains(response, "<svg")
        response = self.client.post("/accounts/mfa/setup/", {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertTrue(self.is_logged_in())
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_confirmed)
        self.assertEqual(self.user.totp_secret, secret)
        self.assertTrue(AuditEvent.objects.filter(action=actions.ACCOUNT_MFA_ENROLLED, actor=self.user).exists())
        self.assertNotIn("mfa_user_id", self.client.session)
        self.assertNotIn("mfa_new_secret", self.client.session)

    def test_setup_with_invalid_code_shows_error(self):
        self.post_login()
        self.client.get("/accounts/mfa/setup/")
        response = self.client.post("/accounts/mfa/setup/", {"code": "000000"})
        self.assertContains(response, "Code not accepted, try again.")
        self.assertFalse(self.is_logged_in())
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_confirmed)

    def test_enrolled_user_goes_to_verify(self):
        self.enroll()
        response = self.post_login()
        self.assertRedirects(response, "/accounts/mfa/verify/", fetch_redirect_response=False)
        self.assertFalse(self.is_logged_in())
        # Setup redirects an already-enrolled user to verify.
        response = self.client.get("/accounts/mfa/setup/")
        self.assertRedirects(response, "/accounts/mfa/verify/", fetch_redirect_response=False)

    def test_verify_valid_code_logs_in(self):
        secret = self.enroll()
        self.post_login()
        response = self.client.post("/accounts/mfa/verify/", {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertTrue(self.is_logged_in())
        self.assertNotIn("mfa_user_id", self.client.session)

    def test_verify_keeps_safe_next(self):
        secret = self.enroll()
        self.post_login(next="/accounts/login/?x=1")
        response = self.client.post("/accounts/mfa/verify/", {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(response, "/accounts/login/?x=1", fetch_redirect_response=False)

    def test_verify_five_bad_codes_resets_sign_in(self):
        self.enroll()
        self.post_login()
        for _ in range(4):
            response = self.client.post("/accounts/mfa/verify/", {"code": "000000"})
            self.assertContains(response, "Code not accepted, try again.")
        response = self.client.post("/accounts/mfa/verify/", {"code": "000000"})
        self.assertRedirects(response, "/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn("mfa_user_id", self.client.session)
        self.assertFalse(self.is_logged_in())
        response = self.client.get("/accounts/login/")
        self.assertContains(response, "Too many attempts, please sign in again.")

    def test_pending_mfa_expires_after_300_seconds(self):
        secret = self.enroll()
        start = time.time()
        with mock.patch("time.time", return_value=start):
            self.post_login()
        with mock.patch("time.time", return_value=start + 301):
            response = self.client.post("/accounts/mfa/verify/", {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(response, "/accounts/login/", fetch_redirect_response=False)
        self.assertFalse(self.is_logged_in())
        response = self.client.get("/accounts/login/")
        self.assertContains(response, "Sign-in expired, please sign in again.")

    def test_mfa_views_without_pending_sign_in_redirect_to_login(self):
        for url in ("/accounts/mfa/setup/", "/accounts/mfa/verify/"):
            response = self.client.get(url)
            self.assertRedirects(response, "/accounts/login/", fetch_redirect_response=False)

    @override_settings(MFA_REQUIRED=False)
    def test_mfa_disabled_logs_in_directly(self):
        response = self.post_login()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertTrue(self.is_logged_in())


class MfaSettingsTests(SimpleTestCase):
    def tearDown(self):
        importlib.reload(project_settings)

    def test_mfa_forced_on_when_debug_off(self):
        env = {"DJANGO_DEBUG": "0", "MFA_REQUIRED": "0", "DJANGO_SECRET_KEY": "x" * 50}
        with mock.patch.dict(os.environ, env):
            reloaded = importlib.reload(project_settings)
            self.assertIs(reloaded.MFA_REQUIRED, True)
