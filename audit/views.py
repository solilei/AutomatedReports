import json

from django.core.paginator import Paginator
from django.shortcuts import render

from accounts.decorators import admin_required
from audit.actions import ACTION_CHOICES
from audit.models import AuditEvent

PAGE_SIZE = 50


@admin_required
def event_list(request):
    events = AuditEvent.objects.all()
    action = request.GET.get("action", "")
    group = request.GET.get("group", "").strip().upper()
    if action:
        events = events.filter(action=action)
    if group:
        events = events.filter(group_number=group)
    page = Paginator(events, PAGE_SIZE).get_page(request.GET.get("page"))
    for event in page:
        event.details_json = json.dumps(event.details, ensure_ascii=False, sort_keys=True)
    filters = {key: value for key, value in (("action", action), ("group", group)) if value}
    return render(
        request,
        "audit/event_list.html",
        {
            "page": page,
            "action": action,
            "group": group,
            "action_choices": ACTION_CHOICES,
            "filter_query": "&".join(f"{k}={v}" for k, v in filters.items()),
        },
    )
