from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower


class Group(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        LOCKED = "locked", "Locked"
        ARCHIVED = "archived", "Archived"

    number = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    # The status an archived group returns to when unarchived; blank otherwise.
    status_before_archive = models.CharField(
        max_length=10, choices=Status.choices, blank=True, default=""
    )
    identity_mode = models.CharField(
        max_length=4, choices=[("id", "Cadet ID"), ("name", "Name")]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]

    @property
    def is_editable(self):
        return self.status == self.Status.ACTIVE

    def __str__(self):
        return self.number


class Cadet(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="cadets")
    name = models.CharField(max_length=200)
    external_id = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "external_id"],
                condition=~Q(external_id=""),
                name="unique_cadet_id_per_group",
            ),
            # Without IDs, names identify cadets ignoring case.
            models.UniqueConstraint(
                F("group"),
                Lower("name"),
                condition=Q(external_id=""),
                name="unique_cadet_name_per_group",
            ),
        ]

    def __str__(self):
        return self.name


class DeletedGroupNumber(models.Model):
    number = models.CharField(max_length=20, unique=True)
    deleted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.number


class RosterColumnPreference(models.Model):
    name_header = models.CharField(max_length=200, blank=True, default="")
    id_header = models.CharField(max_length=200, blank=True, default="")

    @classmethod
    def get(cls):
        return cls.objects.get_or_create(pk=1)[0]


class RosterUpload(models.Model):
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=255)
    file_content = models.BinaryField()
    group_number = models.CharField(max_length=20)
    status = models.CharField(
        max_length=10,
        choices=[("uploaded",) * 2, ("parsed",) * 2, ("applied",) * 2, ("discarded",) * 2],
        default="uploaded",
    )
    name_col = models.IntegerField(null=True)
    id_col = models.IntegerField(null=True)
    parsed = models.JSONField(default=dict)
