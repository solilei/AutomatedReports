from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import services
from accounts.models import User
from accounts.tests.helpers import make_user


class TimeZoneTests(TestCase):
    def test_default_time_zone_is_utc_plus_8(self):
        # Etc/GMT-8 is the IANA name for UTC+8.
        self.assertEqual(settings.TIME_ZONE, "Etc/GMT-8")


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class FailedSignInCounterTests(TestCase):
    def test_parallel_requests_with_stale_user_copies_lose_no_failures(self):
        make_user("inst")
        first = User.objects.get(username="inst")
        second = User.objects.get(username="inst")  # another request's copy, loaded earlier
        for _ in range(2):
            services.record_failed_sign_in(first)
        for _ in range(2):
            services.record_failed_sign_in(second)
        self.assertEqual(User.objects.get(username="inst").failed_sign_ins, 4)

        services.record_failed_sign_in(first)
        user = User.objects.get(username="inst")
        self.assertTrue(services.is_sign_in_locked(user))
        self.assertEqual(user.failed_sign_ins, 0)


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class LastAdminTests(TestCase):
    def test_last_admin_cannot_be_demoted_after_the_other_is(self):
        first = make_user("a", role="admin")
        second = make_user("b", role="admin")
        self.client.force_login(first)
        self.client.post(reverse("accounts:user_demote", args=[second.pk]))
        response = self.client.post(reverse("accounts:user_demote", args=[first.pk]), follow=True)
        self.assertContains(response, "Cannot demote the last remaining admin")
        self.assertEqual(User.objects.filter(role=User.Role.ADMIN).count(), 1)
