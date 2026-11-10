from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from audit import actions
from audit.service import log


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class AuditPaginationTests(TestCase):
    def test_filter_in_page_links_is_url_encoded(self):
        admin = make_user("boss", role="admin")
        self.client.force_login(admin)
        for _ in range(60):
            log(admin, actions.EXPORT_DOWNLOADED, "x", group_number="A&B")
        response = self.client.get(reverse("audit:event_list"), {"group": "a&b"})
        self.assertContains(response, "group=A%26B&amp;page=2")
