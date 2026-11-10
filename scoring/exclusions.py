from roster.models import Cadet

from .models import CadetSubjectExclusion


def excluded_pairs(group):
    """Set of (cadet_id, subject_id) for cadets of `group` taken off a subject."""
    return set(
        CadetSubjectExclusion.objects.filter(cadet__group=group).values_list(
            "cadet_id", "subject_id"
        )
    )


def cadets_taking(group, subject):
    """Active cadets of `group` who take `subject`, in roster order."""
    return (
        Cadet.objects.filter(group=group, is_active=True)
        .exclude(exclusions__subject=subject)
        .order_by("position", "name")
    )
