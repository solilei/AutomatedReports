import importlib
import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from accounts.models import User
from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from config import settings as project_settings

TENANT = "tenant-1"
OID = "11111111-1111-1111-1111-111111111111"
ENTRA = dict(
    LOGIN_MODE="both",
    ENTRA_TENANT_ID=TENANT,
    ENTRA_CLIENT_ID="c",
    ENTRA_CLIENT_SECRET="s",
    ENTRA_REDIRECT_URI="http://localhost:8000/accounts/microsoft/callback/",
    MFA_REQUIRED=False,
)
LOGIN_URL = "/accounts/microsoft/login/"
CALLBACK_URL = "/accounts/microsoft/callback/"


def claims(**extra):
    base = {"tid": TENANT, "oid": OID, "preferred_username": "ada@example.org", "name": "Ada Fake"}
    base.update(extra)
    return base


@override_settings(**ENTRA)
class MicrosoftSignInTests(TestCase):
    def setUp(self):
        patcher = mock.patch("accounts.microsoft.build_msal_app")
        self.app = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.app.initiate_auth_code_flow.return_value = {"auth_uri": "https://login.example/authorize", "state": "x"}

    def start_flow(self):
        self.client.get(LOGIN_URL)

    def callback(self, result=None, **claim_extra):
        self.app.acquire_token_by_auth_code_flow.return_value = (
            result if result is not None else {"id_token_claims": claims(**claim_extra)}
        )
        self.start_flow()
        return self.client.get(CALLBACK_URL, {"code": "abc", "state": "x"})

    @override_settings(LOGIN_MODE="local")
    def test_routes_404_in_local_mode(self):
        self.assertEqual(self.client.get(LOGIN_URL).status_code, 404)
        self.assertEqual(self.client.get(CALLBACK_URL).status_code, 404)

    def test_login_redirects_to_auth_uri_and_stores_flow(self):
        response = self.client.get(LOGIN_URL)
        self.assertRedirects(response, "https://login.example/authorize", fetch_redirect_response=False)
        self.assertEqual(self.client.session["entra_flow"]["state"], "x")
        self.app.initiate_auth_code_flow.assert_called_once_with(
            ["User.Read"], redirect_uri=ENTRA["ENTRA_REDIRECT_URI"]
        )

    def test_first_sign_in_creates_pending_account_without_password(self):
        response = self.callback()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        user = User.objects.get(entra_object_id=OID)
        self.assertEqual(user.username, "ada@example.org")
        self.assertEqual(user.full_name, "Ada Fake")
        self.assertEqual(user.auth_source, User.Source.MICROSOFT)
        self.assertEqual(user.role, User.Role.INSTRUCTOR)
        self.assertFalse(user.is_approved)
        self.assertFalse(user.has_usable_password())
        self.assertRedirects(self.client.get("/"), "/accounts/pending/", fetch_redirect_response=False)
        event = AuditEvent.objects.get(action=actions.ACCOUNT_CREATED)
        self.assertEqual(event.actor_label, "Microsoft first sign-in")

    def test_other_tenant_rejected_and_no_user_created(self):
        response = self.callback(tid="other-tenant")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Accounts from other organisations are not accepted.", status_code=403)
        self.assertFalse(User.objects.filter(entra_object_id=OID).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_existing_approved_user_signs_in(self):
        user = make_user("ada@example.org", auth_source=User.Source.MICROSOFT, entra_object_id=OID)
        response = self.callback()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_deactivated_user_rejected(self):
        make_user("ada@example.org", auth_source=User.Source.MICROSOFT, entra_object_id=OID, is_active=False)
        response = self.callback()
        self.assertContains(response, "This account has been deactivated.", status_code=403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_missing_flow_in_session_returns_400(self):
        response = self.client.get(CALLBACK_URL, {"code": "abc"})
        self.assertContains(response, "Sign-in session expired, please try again.", status_code=400)
        self.app.acquire_token_by_auth_code_flow.assert_not_called()

    def test_msal_error_returns_400(self):
        response = self.callback(result={"error": "invalid_grant"})
        self.assertContains(response, "Microsoft sign-in failed.", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_msal_value_error_returns_400(self):
        self.app.acquire_token_by_auth_code_flow.side_effect = ValueError("state mismatch")
        self.start_flow()
        response = self.client.get(CALLBACK_URL, {"code": "abc", "state": "bad"})
        self.assertContains(response, "Microsoft sign-in failed.", status_code=400)

    def test_flow_is_single_use(self):
        self.callback(result={"error": "invalid_grant"})
        self.assertNotIn("entra_flow", self.client.session)

    def test_username_collision_returns_409(self):
        make_user("ada@example.org")
        response = self.callback()
        self.assertContains(response, "An account named ada@example.org already exists.", status_code=409)
        self.assertFalse(User.objects.filter(entra_object_id=OID).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_approval_grants_access(self):
        self.callback()
        user = User.objects.get(entra_object_id=OID)
        admin = make_user("boss", role="admin")
        self.client.post("/accounts/logout/")
        self.client.force_login(admin)
        self.client.post(f"/accounts/manage/{user.pk}/approve/")
        self.client.post("/accounts/logout/")
        self.callback()
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_microsoft_user_skips_local_mfa(self):
        with override_settings(MFA_REQUIRED=True):
            make_user("ada@example.org", auth_source=User.Source.MICROSOFT, entra_object_id=OID)
            response = self.callback()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)


class MicrosoftSettingsTests(TestCase):
    def reload_settings(self, env):
        with mock.patch.dict(os.environ, env):
            return importlib.reload(project_settings)

    def test_missing_entra_settings_raise_improperly_configured(self):
        clean = {k: "" for k in os.environ if k.startswith("ENTRA_")}
        try:
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "Microsoft sign-in needs ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET and ENTRA_REDIRECT_URI",
            ):
                self.reload_settings({**clean, "LOGIN_MODE": "microsoft"})
        finally:
            importlib.reload(project_settings)

    def test_local_mode_needs_no_entra_settings(self):
        try:
            module = self.reload_settings({"LOGIN_MODE": "local"})
            self.assertEqual(module.ENTRA_TENANT_ID, os.environ.get("ENTRA_TENANT_ID", ""))
        finally:
            importlib.reload(project_settings)
