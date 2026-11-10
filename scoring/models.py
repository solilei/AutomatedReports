import re

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from scoring.attributes import ATTRIBUTE_FIELDS


class Programme(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # Group numbers must be this prefix followed by digits. Blank means no check.
    group_prefix = models.CharField(max_length=10, blank=True, default="")
    is_fixed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def accepts_number(self, number):
        if not self.group_prefix:
            return True
        return bool(re.fullmatch(re.escape(self.group_prefix) + r"\d+", number, re.IGNORECASE))


class Subject(models.Model):
    name = models.CharField(max_length=100)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="subjects")
    instructors = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="assigned_subjects", blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["programme__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["programme", "name"], name="unique_subject_per_programme")
        ]

    @property
    def is_fixed(self):
        return self.programme.is_fixed

    def __str__(self):
        return self.name


class CadetSubjectExclusion(models.Model):
    cadet = models.ForeignKey("roster.Cadet", on_delete=models.CASCADE, related_name="exclusions")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cadet", "subject"], name="unique_exclusion")
        ]


class ScoreSet(models.Model):
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="score_sets"
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    group = models.ForeignKey(
        "roster.Group", on_delete=models.CASCADE, related_name="score_sets"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instructor", "subject", "group"], name="unique_score_set"
            )
        ]


def _score_field():
    return models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )


class CadetScore(models.Model):
    score_set = models.ForeignKey(ScoreSet, on_delete=models.CASCADE, related_name="rows")
    cadet = models.ForeignKey(
        "roster.Cadet", on_delete=models.CASCADE, related_name="scores"
    )
    attentiveness = _score_field()
    motivation = _score_field()
    discipline = _score_field()
    attire = _score_field()
    teamwork = _score_field()
    communication = _score_field()
    comment = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["score_set", "cadet"], name="unique_row_per_cadet"),
            *[
                models.CheckConstraint(
                    condition=Q(**{f"{f}__isnull": True}) | Q(**{f"{f}__gte": 1, f"{f}__lte": 5}),
                    name=f"{f}_1_to_5",
                )
                for f in ATTRIBUTE_FIELDS
            ],
        ]
