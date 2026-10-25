from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from accounts.tests.helpers import make_user
from roster.tests.helpers import make_group
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.models import CadetScore, ScoreSet, Subject
from scoring.tests.helpers import make_score_set


class ScoreModelTests(TestCase):
    def setUp(self):
        self.instructor = make_user("inst")
        self.subject = Subject.objects.create(name="Drill")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        self.alice, self.bob = self.group.cadets.all()

    def test_one_score_set_per_instructor_subject_group(self):
        make_score_set(self.instructor, self.subject, self.group, {})
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScoreSet.objects.create(
                instructor=self.instructor, subject=self.subject, group=self.group
            )

    def test_same_instructor_two_subjects_two_sets(self):
        other = Subject.objects.create(name="Leadership")
        make_score_set(self.instructor, self.subject, self.group, {})
        make_score_set(self.instructor, other, self.group, {})
        self.assertEqual(ScoreSet.objects.count(), 2)

    def test_score_out_of_range_rejected_by_db(self):
        score_set = make_score_set(self.instructor, self.subject, self.group, {})
        for field in ATTRIBUTE_FIELDS:
            for bad in (6, 0):
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        CadetScore.objects.create(
                            score_set=score_set, cadet=self.alice, **{field: bad}
                        )

    def test_blank_scores_allowed(self):
        score_set = make_score_set(self.instructor, self.subject, self.group, {self.alice: {}})
        row = score_set.rows.get()
        for field in ATTRIBUTE_FIELDS:
            self.assertIsNone(getattr(row, field))
        self.assertEqual(row.comment, "")

    def test_deleting_group_cascades_to_sets_and_rows(self):
        make_score_set(
            self.instructor, self.subject, self.group, {self.alice: {"teamwork": 4}}
        )
        self.group.delete()
        self.assertEqual(ScoreSet.objects.count(), 0)
        self.assertEqual(CadetScore.objects.count(), 0)

    def test_deleting_cadet_cascades_to_rows(self):
        score_set = make_score_set(
            self.instructor,
            self.subject,
            self.group,
            {self.alice: {"teamwork": 4}, self.bob: {"teamwork": 3}},
        )
        self.alice.delete()
        self.assertEqual(score_set.rows.count(), 1)
        self.assertEqual(score_set.rows.get().cadet, self.bob)

    def test_instructor_delete_protected(self):
        make_score_set(self.instructor, self.subject, self.group, {})
        with self.assertRaises(ProtectedError):
            self.instructor.delete()
