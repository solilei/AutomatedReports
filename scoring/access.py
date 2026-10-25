from django.http import Http404
from django.shortcuts import get_object_or_404

from roster.models import Group


def get_visible_group(request, number):
    group = get_object_or_404(Group, number=number)
    if group.status == Group.Status.ARCHIVED and not request.user.is_admin:
        raise Http404
    return group
