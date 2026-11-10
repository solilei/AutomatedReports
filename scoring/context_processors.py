from .completeness import missing_scores


def missing_count(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_admin:
        return {"missing_count": len(missing_scores())}
    return {}
