from django.conf import settings
from django.db import models

from audit.actions import ACTION_CHOICES


class AuditEvent(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    actor_label = models.CharField(max_length=150)
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    group_number = models.CharField(max_length=20, blank=True, default="", db_index=True)
    summary = models.CharField(max_length=500)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Audit events are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events cannot be deleted")
