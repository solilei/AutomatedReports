from django.conf import settings
from django.test import SimpleTestCase

from config import settings as project_settings


class SecuritySettingsTests(SimpleTestCase):
    def test_session_idle_timeout_is_30_minutes(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertIs(settings.SESSION_SAVE_EVERY_REQUEST, True)

    def test_default_login_mode_is_local(self):
        self.assertEqual(settings.LOGIN_MODE, "local")

    def test_allowed_hosts_default_localhost_only(self):
        # The test runner appends "testserver" to django.conf.settings, so read the module itself.
        self.assertEqual(project_settings.ALLOWED_HOSTS, ["127.0.0.1", "localhost"])
