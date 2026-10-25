from django.test import TestCase

from accounts.tests.helpers import make_user
from roster.models import Cadet
from roster.tests.helpers import make_group
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.models import Subject
from scoring.results import group_results, round_average
from scoring.tests.helpers import make_score_set


def scores(value=3, **overrides):
    values = {field: value for field in ATTRIBUTE_FIELDS}
    values.update(overrides)
    return values


class ResultsTests(TestCase):
    def setUp(self):
        self.inst1 = make_user("inst1")
        self.inst2 = make_user("inst2")
        self.drill = Subject.objects.create(name="Drill")
        self.lead = Subject.objects.create(name="Leadership")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        self.alice, self.bob = self.group.cadets.all()

    def test_single_set_averages_equal_scores(self):
        make_score_set(
            self.inst1, self.drill, self.group,
            {self.alice: scores(attentiveness=5, motivation=4, discipline=3,
                                attire=2, teamwork=1, communication=5)},
        )
        result = group_results(self.group)[0]
        self.assertEqual(
            result.averages,
            {"attentiveness": 5, "motivation": 4, "discipline": 3,
             "attire": 2, "teamwork": 1, "communication": 5},
        )
        self.assertEqual(result.number, 1)
        self.assertEqual(result.cadet, self.alice)

    def test_average_across_instructors_and_subjects(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(5)})
        make_score_set(self.inst2, self.drill, self.group, {self.alice: scores(4)})
        make_score_set(self.inst1, self.lead, self.group, {self.alice: scores(4)})
        result = group_results(self.group)[0]
        self.assertEqual(set(result.averages.values()), {4})  # 13/3 = 4.33

    def test_blank_in_saved_set_counts_as_3(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(5, teamwork=None)})
        make_score_set(self.inst2, self.drill, self.group, {self.alice: scores(5, teamwork=5)})
        result = group_results(self.group)[0]
        self.assertEqual(result.averages["teamwork"], 4)  # (3 + 5) / 2
        self.assertEqual(result.averages["attire"], 5)

    def test_cadet_missing_from_a_saved_set_counts_as_3_in_it(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(5), self.bob: scores(5)})
        # Saved before Bob joined the group, so it has no row for him.
        make_score_set(self.inst2, self.drill, self.group, {self.alice: scores(5)})
        bob = group_results(self.group)[1]
        self.assertEqual(set(bob.averages.values()), {4})  # (5 + 3) / 2
        self.assertEqual(bob.total, 24)
        self.assertEqual(set(group_results(self.group)[0].averages.values()), {5})

    def test_cadet_without_rows_is_no_data(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(4)})
        results = group_results(self.group)
        self.assertIsNone(results[1].averages)
        self.assertIsNone(results[1].total)
        self.assertFalse(results[1].flagged)

    def test_cadet_added_after_save_counts_as_3_for_that_set(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(5)})
        make_score_set(self.inst2, self.drill, self.group, {self.alice: scores(5)})
        carol = Cadet.objects.create(group=self.group, name="Carol Poe", position=3)
        make_score_set(self.inst1, self.lead, self.group, {carol: scores(1)})
        results = group_results(self.group)
        self.assertEqual(results[2].cadet, carol)
        self.assertEqual(set(results[2].averages.values()), {2})  # (1 + 3 + 3) / 3 = 2.33
        self.assertIsNone(results[1].averages)

    def test_inactive_cadets_excluded(self):
        make_score_set(self.inst1, self.drill, self.group,
                       {self.alice: scores(4), self.bob: scores(4)})
        self.bob.is_active = False
        self.bob.save()
        results = group_results(self.group)
        self.assertEqual([r.cadet for r in results], [self.alice])

    def test_results_ordered_and_numbered(self):
        results = group_results(self.group)
        self.assertEqual([(r.number, r.cadet) for r in results],
                         [(1, self.alice), (2, self.bob)])

    def test_other_group_scores_ignored(self):
        other = make_group("C217", cadets=("Alice Ng",))
        make_score_set(self.inst1, self.drill, other, {other.cadets.get(): scores(1)})
        self.assertIsNone(group_results(self.group)[0].averages)

    def test_round_average_half_up_to_whole_number(self):
        self.assertEqual(round_average(5, 2), 3)   # 2.5
        self.assertEqual(round_average(7, 3), 2)   # 2.33
        self.assertEqual(round_average(5, 3), 2)   # 1.67
        self.assertEqual(round_average(9, 2), 5)   # 4.5
        self.assertEqual(round_average(13, 3), 4)  # 4.33

    def test_averages_are_ints(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(4)})
        make_score_set(self.inst2, self.drill, self.group, {self.alice: scores(3)})
        result = group_results(self.group)[0]
        for value in result.averages.values():
            self.assertIs(type(value), int)
        self.assertIs(type(result.total), int)

    def test_flag_when_any_average_below_2_5(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(4, attire=2)})
        make_score_set(self.inst2, self.drill, self.group, {self.alice: scores(4, attire=2)})
        make_score_set(self.inst1, self.lead, self.group, {self.alice: scores(4, attire=3)})
        result = group_results(self.group)[0]
        self.assertEqual(result.averages["attire"], 2)
        self.assertTrue(result.flagged)

    def test_not_flagged_at_exactly_2_5(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(4, attire=2)})
        make_score_set(self.inst2, self.drill, self.group, {self.alice: scores(4, attire=3)})
        result = group_results(self.group)[0]
        self.assertEqual(result.averages["attire"], 3)
        self.assertFalse(result.flagged)

    def test_total_is_sum_of_whole_number_averages_range_6_to_30(self):
        make_score_set(
            self.inst1, self.drill, self.group,
            {self.alice: scores(5), self.bob: scores(1)},
        )
        make_score_set(
            self.inst2, self.drill, self.group,
            {self.alice: scores(4, teamwork=5), self.bob: scores(2)},
        )
        alice, bob = group_results(self.group)
        # 4.5 rounds to 5 for every attribute (teamwork: 5)
        self.assertEqual(alice.total, 30)
        # 1.5 rounds to 2
        self.assertEqual(bob.total, 12)
        self.assertTrue(6 <= bob.total <= alice.total <= 30)

    def test_deactivated_instructor_scores_still_count(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(5)})
        self.inst1.is_active = False
        self.inst1.save()
        self.assertEqual(set(group_results(self.group)[0].averages.values()), {5})

    def test_query_count_constant(self):
        make_score_set(self.inst1, self.drill, self.group, {self.alice: scores(4)})
        with self.assertNumQueries(2):
            group_results(self.group)
        big = make_group("C217", cadets=tuple(f"Cadet {i:02d}" for i in range(20)))
        make_score_set(self.inst1, self.drill, big, {c: scores(4) for c in big.cadets.all()})
        with self.assertNumQueries(2):
            group_results(big)
