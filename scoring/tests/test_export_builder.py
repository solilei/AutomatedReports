from datetime import date
from io import BytesIO

from django.test import TestCase
from openpyxl import load_workbook

from accounts.tests.helpers import make_user
from roster.models import Cadet
from roster.tests.helpers import make_group
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.export import build_group_report
from scoring.models import CadetScore, Subject
from scoring.tests.helpers import make_score_set

EXPORT_DATE = date(2026, 10, 25)
BANDS = [
    ("Excellent", "A", "90-100", 5, "66FF33"),
    ("Above standard", "B", "80-89", 4, "C6E0B4"),
    ("Meet standard", "C", "70-79", 3, "E2EFDA"),
    ("Below standard", "D", "60-69", 2, "FFC000"),
    ("Unacceptable", "E", "<60", 1, "FF0000"),
]
BAND_COLUMNS = ["C", "F", "I", "L", "N"]
BAND_MERGES = ["C{r}:E{r}", "F{r}:H{r}", "I{r}:K{r}", "L{r}:M{r}", "N{r}:O{r}"]
ATTRIBUTE_COLUMNS = ["C", "E", "G", "I", "K", "M"]


def scores(value=3, **overrides):
    values = {field: value for field in ATTRIBUTE_FIELDS}
    values.update(overrides)
    return values


def rgb(cell):
    return cell.fill.fgColor.rgb[-6:]


class ExportBuilderTests(TestCase):
    def setUp(self):
        self.bea = make_user("bea", full_name="bea Tan")
        self.carl = make_user("carl", full_name="")
        self.drill = Subject.objects.create(name="Drill")
        self.lead = Subject.objects.create(name="Leadership")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray", "Cy Poe"))
        self.alice, self.bob, self.cy = self.group.cadets.all()

    def build(self):
        return build_group_report(self.group, EXPORT_DATE)

    def sheet(self):
        return self.build().active

    def merges(self, ws):
        return {str(r) for r in ws.merged_cells.ranges}

    def test_sheet_title_is_group_number(self):
        wb = self.build()
        self.assertEqual(wb.sheetnames, ["C216"])

    def test_header_texts_and_course(self):
        ws = self.sheet()
        self.assertEqual(ws["A1"].value, "Course C216")
        self.assertTrue(ws["A1"].font.bold)
        self.assertEqual(ws["A1"].alignment.vertical, "center")
        self.assertEqual(ws["D1"].value, "Cadet Soft Skills Report")
        self.assertTrue(ws["D1"].font.bold)
        self.assertEqual(ws["D1"].font.size, 18)
        self.assertEqual(ws["C2"].value, "Ground School Department")
        self.assertTrue(ws["C2"].font.bold)
        self.assertLessEqual({"A1:B3", "C2:I2"}, self.merges(ws))
        widths = {c: ws.column_dimensions[c].width for c in "ABCO"}
        self.assertEqual(widths, {"A": 3.82, "B": 29.73, "C": 8.36, "O": 6.73})
        for col in "DEFGHIJKLMN":
            self.assertEqual(ws.column_dimensions[col].width, 8.36)
        ws = self.sheet()
        self.assertEqual(ws.page_setup.orientation, "landscape")
        self.assertEqual(ws.page_setup.paperSize, 9)
        margins = ws.page_margins
        self.assertEqual(
            (margins.left, margins.right, margins.top, margins.bottom, margins.header, margins.footer),
            (0.25, 0.25, 0.75, 0.75, 0.3, 0.3),
        )

    def test_instruction_text_exact(self):
        ws = self.sheet()
        self.assertEqual(
            ws["A4"].value,
            "Please rate your observations of individual cadet from 1 to 5 using the grading "
            "system and upload in appropriate GSH shared folder for your group of subjects.",
        )
        self.assertEqual(
            ws["A5"].value,
            "C is the minimum required standard. Students falling in Below C Grade will be "
            "consulted by HGS and the event will be documented.",
        )
        self.assertEqual(
            ws["A6"].value,
            "If after consultation observations remains below C, the individual will be "
            "referred to the sponsor.",
        )
        self.assertEqual(
            ws["A7"].value,
            "This report will be used by HGS as part of the documentation required for the "
            "completion of Cadets Final Ground Training Report.",
        )

    def test_instructor_and_subject_header_lists(self):
        make_score_set(self.carl, self.lead, self.group, {self.alice: scores()})
        make_score_set(self.bea, self.drill, self.group, {self.alice: scores()})
        make_score_set(self.bea, self.lead, self.group, {self.alice: scores()})
        other = make_group("C217", cadets=("Zed One",))
        other_user = make_user("zed", full_name="Zed Other")
        make_score_set(other_user, self.drill, other, {other.cadets.get(): scores()})
        ws = self.sheet()
        # case-insensitive sort: "bea Tan" before "carl"; the C217 instructor is excluded
        self.assertEqual(ws["B8"].value, "Instructor: bea Tan, carl")
        self.assertEqual(ws["C8"].value, "Subject:")
        self.assertEqual(ws["D8"].value, "Drill, Leadership")

    def test_date_cell_value_and_format(self):
        ws = self.sheet()
        self.assertEqual(ws["M8"].value, "Date")
        value = ws["N8"].value
        self.assertEqual(getattr(value, "date", lambda: value)(), EXPORT_DATE)
        self.assertEqual(ws["N8"].number_format, "DD/MM/YYYY")
        self.assertIn("N8:O8", self.merges(ws))

    def test_grading_key_values_and_fills(self):
        ws = self.sheet()
        merges = self.merges(ws)
        self.assertEqual(ws["B9"].value, "Grading System")
        self.assertIn("B9:B10", merges)
        self.assertEqual(ws["B11"].value, "%")
        self.assertEqual(ws["B12"].value, "Points")
        for i, (label, grade, percent, points, hex_) in enumerate(BANDS):
            col = BAND_COLUMNS[i]
            for row, expected in ((9, label), (10, grade), (11, percent), (12, points)):
                cell = ws[f"{col}{row}"]
                self.assertEqual(cell.value, expected, f"{col}{row}")
                self.assertEqual(cell.fill.fill_type, "solid")
                self.assertEqual(rgb(cell), hex_, f"{col}{row}")
                self.assertIn(BAND_MERGES[i].format(r=row), merges)
        self.assertIsInstance(ws["C12"].value, int)
        for col in "BCDEFGHIJKLMNO":
            cell = ws[f"{col}13"]
            self.assertIsNone(cell.value)
            self.assertEqual(cell.fill.fill_type, "solid")
            self.assertEqual(rgb(cell), "000000")

    def test_table_header_row_and_merges(self):
        ws = self.sheet()
        merges = self.merges(ws)
        self.assertEqual(ws["A14"].value, "No.")
        self.assertEqual(ws["B14"].value, "Name")
        labels = [
            "Attentiveness Engagement",
            "Motivation Diligence Enthusiasm",
            "Discipline Courtesy",
            "Attire Appearance",
            "Teamwork",
            "Comms. Participation Interaction",
        ]
        pairs = ["C14:D14", "E14:F14", "G14:H14", "I14:J14", "K14:L14", "M14:N14"]
        for col, label, pair in zip(ATTRIBUTE_COLUMNS, labels, pairs):
            self.assertEqual(ws[f"{col}14"].value, label)
            self.assertIn(pair, merges)
        self.assertEqual(ws["O14"].value, "Total\nPoint")
        for col in "ABCEGIKMO":
            cell = ws[f"{col}14"]
            self.assertTrue(cell.font.bold, col)
            self.assertTrue(cell.alignment.wrap_text, col)
            self.assertEqual(cell.alignment.horizontal, "center", col)

    def test_cadet_rows_values_fills_and_sum_formula(self):
        make_score_set(
            self.bea, self.drill, self.group,
            {self.alice: scores(attentiveness=5, motivation=4, discipline=3,
                                attire=2, teamwork=1, communication=5)},
        )
        ws = self.sheet()
        merges = self.merges(ws)
        self.assertEqual(ws["A15"].value, 1)
        self.assertEqual(ws["B15"].value, "Alice Ng")
        expected = [5, 4, 3, 2, 1, 5]
        for col, value in zip(ATTRIBUTE_COLUMNS, expected):
            cell = ws[f"{col}15"]
            self.assertEqual(cell.value, value)
            self.assertIsInstance(cell.value, int)
            self.assertEqual(cell.number_format, "0")
            self.assertEqual(cell.fill.fill_type, "solid")
            self.assertEqual(rgb(cell), BANDS[5 - value][4])
        for pair in ("C15:D15", "E15:F15", "G15:H15", "I15:J15", "K15:L15", "M15:N15"):
            self.assertIn(pair, merges)
        self.assertEqual(ws["O15"].value, "=SUM(C15:N15)")
        self.assertEqual(ws["O15"].number_format, "0")
        self.assertEqual(ws["A16"].value, 2)
        self.assertEqual(ws["B16"].value, "Bob Ray")

    def test_no_data_row(self):
        make_score_set(self.bea, self.drill, self.group, {self.alice: scores(4)})
        ws = self.sheet()
        self.assertEqual(ws["A16"].value, 2)
        self.assertEqual(ws["B16"].value, "Bob Ray")
        for col in ATTRIBUTE_COLUMNS:
            self.assertEqual(ws[f"{col}16"].value, "n/a")
        self.assertEqual(ws["O16"].value, "no data")
        self.assertEqual(ws["O15"].value, "=SUM(C15:N15)")

    def test_inactive_cadets_excluded(self):
        make_score_set(self.bea, self.drill, self.group,
                       {self.alice: scores(4), self.bob: scores(4)})
        self.bob.is_active = False
        self.bob.save()
        ws = self.sheet()
        self.assertEqual(ws["B15"].value, "Alice Ng")
        self.assertEqual(ws["B16"].value, "Cy Poe")
        self.assertEqual(ws["A16"].value, 2)
        self.assertIsNone(ws["B17"].value)
        self.assertEqual(
            ws["A17"].value,
            "For Additional comments specific to an individual cadet refer to next page.",
        )

    def test_borders_on_table(self):
        ws = self.sheet()
        for row in range(14, 18):
            for col in "ABCDEFGHIJKLMNO":
                border = ws[f"{col}{row}"].border
                for side in ("left", "right", "top", "bottom"):
                    self.assertEqual(getattr(border, side).style, "medium", f"{col}{row} {side}")

    def comment(self, set_, cadet, text):
        CadetScore.objects.filter(score_set=set_, cadet=cadet).update(comment=text)

    def test_comments_section_format_and_order(self):
        s1 = make_score_set(self.carl, self.drill, self.group,
                            {self.alice: scores(), self.bob: scores()})
        s2 = make_score_set(self.bea, self.lead, self.group, {self.alice: scores()})
        s3 = make_score_set(self.bea, self.drill, self.group, {self.alice: scores()})
        self.comment(s1, self.bob, "  Late twice  ")
        self.comment(s1, self.alice, "Good effort")
        self.comment(s2, self.alice, "Lead well")
        self.comment(s3, self.alice, "Sharp")
        ws = self.sheet()
        footer = 15 + 3
        self.assertEqual(ws[f"A{footer + 4}"].value, "Additional comments, if any:")
        self.assertTrue(ws[f"A{footer + 4}"].font.bold)
        lines = [ws[f"A{footer + 5 + i}"].value for i in range(4)]
        self.assertEqual(
            lines,
            [
                "Alice Ng — bea Tan (Drill): Sharp",
                "Alice Ng — bea Tan (Leadership): Lead well",
                "Alice Ng — carl (Drill): Good effort",
                "Bob Ray — carl (Drill): Late twice",
            ],
        )
        self.assertIsNone(ws[f"A{footer + 9}"].value)
        merges = self.merges(ws)
        for i in range(4):
            row = footer + 5 + i
            self.assertIn(f"A{row}:O{row}", merges)
            self.assertTrue(ws[f"A{row}"].alignment.wrap_text)

    def test_comments_skip_inactive_cadets_and_blank_comments(self):
        s1 = make_score_set(self.bea, self.drill, self.group,
                            {self.alice: scores(), self.bob: scores(), self.cy: scores()})
        self.comment(s1, self.alice, "   ")
        self.comment(s1, self.bob, "Hidden")
        self.comment(s1, self.cy, "Visible")
        self.bob.is_active = False
        self.bob.save()
        ws = self.sheet()
        footer = 15 + 2
        self.assertEqual(ws[f"A{footer + 5}"].value, "Cy Poe — bea Tan (Drill): Visible")
        self.assertIsNone(ws[f"A{footer + 6}"].value)

    def test_no_comments_writes_none(self):
        make_score_set(self.bea, self.drill, self.group, {self.alice: scores()})
        ws = self.sheet()
        footer = 15 + 3
        self.assertEqual(ws[f"A{footer + 4}"].value, "Additional comments, if any:")
        self.assertEqual(ws[f"A{footer + 5}"].value, "None.")

    def test_footer_row_and_page_break_position(self):
        ws = self.sheet()
        footer = 15 + 3
        self.assertEqual(
            ws[f"A{footer}"].value,
            "For Additional comments specific to an individual cadet refer to next page.",
        )
        self.assertIn(f"A{footer}:O{footer}", self.merges(ws))
        self.assertEqual([b.id for b in ws.row_breaks.brk], [footer])

    def test_workbook_saves_and_reloads(self):
        make_score_set(self.bea, self.drill, self.group, {self.alice: scores(4)})
        buffer = BytesIO()
        self.build().save(buffer)
        buffer.seek(0)
        reloaded = load_workbook(buffer)
        self.assertEqual(reloaded.sheetnames, ["C216"])
        self.assertEqual(reloaded.active["B15"].value, "Alice Ng")
        self.assertEqual(reloaded.active["O15"].value, "=SUM(C15:N15)")

    def test_title_rows_are_18pt_calibri(self):
        ws = self.sheet()
        for ref in ("A1", "D1", "C2"):
            self.assertEqual(ws[ref].font.size, 18, ref)
            self.assertEqual(ws[ref].font.name, "Calibri", ref)

    def test_all_other_text_is_calibri_12(self):
        make_score_set(self.bea, self.drill, self.group, {self.alice: scores(4)})
        ws = self.sheet()
        checked = 0
        for row in ws.iter_rows(min_row=4):
            for cell in row:
                if cell.value is None:
                    continue
                checked += 1
                self.assertEqual(cell.font.name, "Calibri", cell.coordinate)
                self.assertEqual(cell.font.size, 12, cell.coordinate)
        self.assertGreater(checked, 0)

    def test_tables_bold_centered_with_medium_black_borders(self):
        make_score_set(self.bea, self.drill, self.group, {self.alice: scores(4)})
        ws = self.sheet()
        cells = [f"{col}{row}" for row in range(14, 18) for col in "ABCDEFGHIJKLMNO"]
        cells += [f"{col}{row}" for row in range(9, 13) for col in "BCDEFGHIJKLMNO"]
        for ref in cells:
            cell = ws[ref]
            self.assertTrue(cell.font.bold, ref)
            self.assertEqual(cell.alignment.horizontal, "center", ref)
            self.assertEqual(cell.alignment.vertical, "center", ref)
            for side in ("left", "right", "top", "bottom"):
                border = getattr(cell.border, side)
                self.assertEqual(border.style, "medium", f"{ref} {side}")
                self.assertEqual(border.color.rgb[-6:], "000000", f"{ref} {side}")

    def test_no_data_row_merges_na_per_attribute(self):
        make_score_set(self.bea, self.drill, self.group, {self.alice: scores(4)})
        ws = self.sheet()
        merges = self.merges(ws)
        for first, last in zip("CEGIKM", "DFHJLN"):
            self.assertIn(f"{first}16:{last}16", merges)
            self.assertEqual(ws[f"{first}16"].value, "n/a")
