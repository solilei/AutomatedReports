from django.shortcuts import redirect
from django.urls import Resolver404, resolve

EXEMPT_VIEW_NAMES = {
    "accounts:login",
    "accounts:logout",
    "accounts:pending",
    "accounts:password_set",
    "accounts:mfa_setup",
    "accounts:mfa_verify",
    "accounts:microsoft_login",
    "accounts:microsoft_callback",
}


class AccessGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return None
        if match.view_name in EXEMPT_VIEW_NAMES:
            return None
        if not request.user.is_approved:
            return redirect("accounts:pending")
        if request.user.must_change_password:
            return redirect("accounts:password_set")
        return None
