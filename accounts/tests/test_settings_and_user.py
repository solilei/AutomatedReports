from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import User


class SettingsAndUserTests(TestCase):
    def test_custom_user_model_is_active(self):
        self.assertIs(get_user_model(), User)

    def test_user_defaults(self):
        user = User.objects.create_user(username="u1", password="x")
        self.assertEqual(user.role, "instructor")
        self.assertEqual(user.auth_source, "local")
        self.assertFalse(user.is_approved)
        self.assertFalse(user.must_change_password)
        self.assertFalse(user.totp_confirmed)
        self.assertIsNone(user.entra_object_id)

    def test_is_admin_property(self):
        self.assertTrue(User(username="a", role="admin").is_admin)
        self.assertFalse(User(username="i", role="instructor").is_admin)

    def test_display_name_falls_back_to_username(self):
        self.assertEqual(User(username="u1", full_name="Pat Lee").display_name, "Pat Lee")
        self.assertEqual(User(username="u1", full_name="").display_name, "u1")

    def test_admin_site_not_installed(self):
        self.assertNotIn("django.contrib.admin", settings.INSTALLED_APPS)

    def test_sqlite_is_default_engine(self):
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3")
