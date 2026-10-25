from io import BytesIO

from django.db import IntegrityError, transaction
from django.test import TestCase
from openpyxl import load_workbook

from roster.models import Cadet, Group, RosterColumnPreference
from roster.tests.helpers import make_group, make_xlsx


class GroupTests(TestCase):
    def test_group_number_unique(self):
        make_group("C216")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Group.objects.create(number="C216", identity_mode="name")

    def test_is_editable_only_when_active(self):
        self.assertTrue(make_group("A1", status="active").is_editable)
        self.assertFalse(make_group("A2", status="locked").is_editable)
        self.assertFalse(make_group("A3", status="archived").is_editable)

    def test_str_is_number(self):
        self.assertEqual(str(make_group("C216")), "C216")


class CadetTests(TestCase):
    def setUp(self):
        self.group = make_group("C216", cadets=())

    def test_cadet_name_unique_per_group_without_id(self):
        Cadet.objects.create(group=self.group, name="Alice Ng", position=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cadet.objects.create(group=self.group, name="Alice Ng", position=2)
        other = make_group("C217", cadets=())
        Cadet.objects.create(group=other, name="Alice Ng", position=1)

    def test_same_name_allowed_with_different_ids(self):
        Cadet.objects.create(group=self.group, name="Alice Ng", external_id="1", position=1)
        Cadet.objects.create(group=self.group, name="Alice Ng", external_id="2", position=2)
        self.assertEqual(self.group.cadets.count(), 2)

    def test_cadet_id_unique_per_group(self):
        Cadet.objects.create(group=self.group, name="Alice Ng", external_id="1", position=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cadet.objects.create(group=self.group, name="Bob Ray", external_id="1", position=2)
        other = make_group("C217", cadets=())
        Cadet.objects.create(group=other, name="Bob Ray", external_id="1", position=1)

    def test_cadets_ordered_by_position(self):
        group = make_group("C300", cadets=("Zed", "Amy", "Mia"))
        self.assertEqual([c.name for c in group.cadets.all()], ["Zed", "Amy", "Mia"])
        self.assertEqual([c.position for c in group.cadets.all()], [1, 2, 3])
        self.assertTrue(all(c.is_active for c in group.cadets.all()))


class ColumnPreferenceTests(TestCase):
    def test_column_preference_singleton(self):
        first = RosterColumnPreference.get()
        first.name_header = "Cadet"
        first.save()
        second = RosterColumnPreference.get()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.name_header, "Cadet")
        self.assertEqual(RosterColumnPreference.objects.count(), 1)
        self.assertEqual(second.id_header, "")


class HelperTests(TestCase):
    def test_make_xlsx_roundtrip(self):
        rows = [["Group", "Name"], ["C216", "Alice Ng"], ["C216", "Bob Ray"]]
        sheet = load_workbook(BytesIO(make_xlsx(rows))).worksheets[0]
        self.assertEqual([list(r) for r in sheet.iter_rows(values_only=True)], rows)
