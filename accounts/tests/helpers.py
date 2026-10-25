from accounts.models import User


def make_user(username="inst", role="instructor", password="correct-horse-battery", **extra):
    user = User.objects.create_user(
        username=username,
        password=password,
        role=role,
        is_approved=True,
        is_active=True,
        auth_source=User.Source.LOCAL,
    )
    for key, value in extra.items():
        setattr(user, key, value)
    if extra:
        user.save()
    return user
