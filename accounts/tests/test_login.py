import time
from unittest import mock

from django.test import Client, TestCase, override_settings

from accounts.tests.helpers import make_user

PASSWORD = "correct-horse-battery"


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class LoginTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def post_login(self, **extra):
        data = {"username": "inst", "password": PASSWORD, **extra}
        return self.client.post("/accounts/login/", data)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/login/?next=/", fetch_redirect_response=False)

    def test_login_page_renders_local_form(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="password"')
        self.assertNotContains(response, "/accounts/microsoft/login/")

    def test_login_success_redirects_home(self):
        response = self.post_login()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_login_respects_safe_next(self):
        response = self.client.post(
            "/accounts/login/", {"username": "inst", "password": PASSWORD, "next": "/accounts/login/?x=1"}
        )
        self.assertRedirects(response, "/accounts/login/?x=1", fetch_redirect_response=False)

    def test_login_ignores_external_next(self):
        response = self.post_login(next="https://evil.example/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_login_wrong_password_shows_error(self):
        response = self.client.post("/accounts/login/", {"username": "inst", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        response = self.post_login()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_get_login_redirects_home(self):
        self.client.force_login(self.user)
        response = self.client.get("/accounts/login/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)

    def test_logout_post_logs_out(self):
        self.client.force_login(self.user)
        response = self.client.post("/accounts/logout/")
        self.assertRedirects(response, "/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_home_shows_nav_and_sign_out(self):
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertContains(response, "<h1>Home</h1>", html=True)
        self.assertContains(response, "Sign out")
        self.assertContains(response, "inst")

    @override_settings(LOGIN_MODE="microsoft")
    def test_microsoft_mode_hides_local_form_and_rejects_post(self):
        response = self.client.get("/accounts/login/")
        self.assertNotContains(response, 'type="password"')
        self.assertContains(response, "/accounts/microsoft/login/")
        self.assertEqual(self.post_login().status_code, 400)

    @override_settings(LOGIN_MODE="both")
    def test_both_mode_shows_both(self):
        response = self.client.get("/accounts/login/")
        self.assertContains(response, 'type="password"')
        self.assertContains(response, "/accounts/microsoft/login/")


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class LoginLockoutTests(TestCase):
    LOCKED = "Too many failed sign-in attempts"

    def setUp(self):
        self.user = make_user()

    def attempt(self, password=PASSWORD, client=None, username="inst"):
        client = client or self.client
        return client.post("/accounts/login/", {"username": username, "password": password})

    def fail(self, times, **kwargs):
        for _ in range(times):
            self.attempt("wrong", **kwargs)

    def test_five_failures_block_even_the_right_password(self):
        self.fail(5)
        response = self.attempt()
        self.assertContains(response, self.LOCKED)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_four_failures_do_not_block(self):
        self.fail(4)
        self.assertRedirects(self.attempt(), "/", fetch_redirect_response=False)

    def test_lock_applies_from_another_browser(self):
        self.fail(5)
        other = Client()
        self.assertContains(self.attempt(client=other), self.LOCKED)
        self.assertNotIn("_auth_user_id", other.session)

    def test_lock_does_not_affect_other_users(self):
        make_user("other")
        self.fail(5)
        response = self.attempt(username="other")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_success_resets_the_count(self):
        self.fail(4)
        self.attempt()
        self.client.post("/accounts/logout/")
        self.fail(4)
        self.assertRedirects(self.attempt(), "/", fetch_redirect_response=False)

    def test_lock_expires_after_15_minutes(self):
        start = time.time()
        with mock.patch("time.time", return_value=start):
            self.fail(5)
        with mock.patch("time.time", return_value=start + 14 * 60):
            self.assertContains(self.attempt(), self.LOCKED)
        with mock.patch("time.time", return_value=start + 15 * 60 + 1):
            self.assertRedirects(self.attempt(), "/", fetch_redirect_response=False)
