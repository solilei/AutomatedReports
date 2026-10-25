from copy import copy
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.pagebreak import Break

from scoring.attributes import ATTRIBUTES
from scoring.models import CadetScore, ScoreSet
from scoring.results import BAND_HEX, group_results

INSTRUCTIONS = [
    "Please rate your observations of individual cadet from 1 to 5 using the grading system "
    "and upload in appropriate GSH shared folder for your group of subjects.",
    "C is the minimum required standard. Students falling in Below C Grade will be consulted "
    "by HGS and the event will be documented.",
    "If after consultation observations remains below C, the individual will be referred to "
    "the sponsor.",
    "This report will be used by HGS as part of the documentation required for the "
    "completion of Cadets Final Ground Training Report.",
]
# (label, grade, percent, points, first column, last column) for the grading-system key
KEY_BANDS = [
    ("Excellent", "A", "90-100", 5, "C", "E"),
    ("Above standard", "B", "80-89", 4, "F", "H"),
    ("Meet standard", "C", "70-79", 3, "I", "K"),
    ("Below standard", "D", "60-69", 2, "L", "M"),
    ("Unacceptable", "E", "<60", 1, "N", "O"),
]
# (first column, last column) of each attribute's merged pair, in ATTRIBUTES order
ATTRIBUTE_PAIRS = [("C", "D"), ("E", "F"), ("G", "H"), ("I", "J"), ("K", "L"), ("M", "N")]
ALL_COLUMNS = "ABCDEFGHIJKLMNO"
FOOTER_TEXT = "For Additional comments specific to an individual cadet refer to next page."
MEDIUM = Side(style="medium", color="000000")
BORDER = Border(left=MEDIUM, right=MEDIUM, top=MEDIUM, bottom=MEDIUM)
BOLD = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _fill(hex_):
    return PatternFill(fill_type="solid", fgColor=hex_, bgColor=hex_)


def _fill_range(ws, first, last, row, hex_):
    for col in ALL_COLUMNS[ALL_COLUMNS.index(first) : ALL_COLUMNS.index(last) + 1]:
        ws[f"{col}{row}"].fill = _fill(hex_)


def build_group_report(group, export_date: date) -> Workbook:
    results = group_results(group)
    score_sets = list(ScoreSet.objects.filter(group=group).select_related("instructor", "subject"))

    wb = Workbook()
    ws = wb.active
    ws.title = group.number

    ws.column_dimensions["A"].width = 3.82
    ws.column_dimensions["B"].width = 29.73
    for col in "CDEFGHIJKLMN":
        ws.column_dimensions[col].width = 8.36
    ws.column_dimensions["O"].width = 6.73

    ws.merge_cells("A1:B3")
    ws["A1"] = f"Course {group.number}"
    ws["A1"].font = Font(bold=True)
    ws["A1"].alignment = Alignment(vertical="center")
    ws["D1"] = "Cadet Soft Skills Report"
    ws["D1"].font = Font(bold=True, size=14)
    ws.merge_cells("C2:I2")
    ws["C2"] = "Ground School Department"

    for row, text in enumerate(INSTRUCTIONS, start=4):
        ws[f"A{row}"] = text

    instructors = sorted({s.instructor.display_name for s in score_sets}, key=str.casefold)
    subjects = sorted({s.subject.name for s in score_sets})
    ws["B8"] = f"Instructor: {', '.join(instructors)}"
    ws["C8"] = "Subject:"
    ws["D8"] = ", ".join(subjects)
    ws["M8"] = "Date"
    ws.merge_cells("N8:O8")
    ws["N8"] = export_date
    ws["N8"].number_format = "DD/MM/YYYY"

    ws.merge_cells("B9:B10")
    ws["B9"] = "Grading System"
    ws["B11"] = "%"
    ws["B12"] = "Points"
    for label, grade, percent, points, first, last in KEY_BANDS:
        for row, value in ((9, label), (10, grade), (11, percent), (12, points)):
            ws.merge_cells(f"{first}{row}:{last}{row}")
            ws[f"{first}{row}"] = value
            _fill_range(ws, first, last, row, BAND_HEX[points])

    for col in ALL_COLUMNS[1:]:
        ws[f"{col}13"].fill = _fill("000000")

    ws["A14"] = "No."
    ws["B14"] = "Name"
    for (_, _, label), (first, last) in zip(ATTRIBUTES, ATTRIBUTE_PAIRS):
        ws.merge_cells(f"{first}14:{last}14")
        ws[f"{first}14"] = label
    ws["O14"] = "Total\nPoint"
    for col in ALL_COLUMNS:
        ws[f"{col}14"].font = Font(bold=True)
        ws[f"{col}14"].alignment = CENTER

    for offset, result in enumerate(results):
        row = 15 + offset
        ws[f"A{row}"] = result.number
        ws[f"B{row}"] = result.cadet.name
        if result.averages is None:
            ws[f"O{row}"] = "no data"
            for first, last in ATTRIBUTE_PAIRS:
                ws.merge_cells(f"{first}{row}:{last}{row}")
                ws[f"{first}{row}"] = "n/a"
            continue
        for (field, _, _), (first, last) in zip(ATTRIBUTES, ATTRIBUTE_PAIRS):
            average = result.averages[field]
            ws.merge_cells(f"{first}{row}:{last}{row}")
            ws[f"{first}{row}"] = average
            ws[f"{first}{row}"].number_format = "0"
            _fill_range(ws, first, last, row, BAND_HEX[average])
        ws[f"O{row}"] = f"=SUM(C{row}:N{row})"
        ws[f"O{row}"].number_format = "0"

    last_row = 14 + len(results)
    for row in range(14, last_row + 1):
        for col in ALL_COLUMNS:
            ws[f"{col}{row}"].border = BORDER
            ws[f"{col}{row}"].font = BOLD
            ws[f"{col}{row}"].alignment = CENTER
    for row in range(9, 13):
        for col in ALL_COLUMNS[1:]:
            ws[f"{col}{row}"].border = BORDER
            ws[f"{col}{row}"].font = BOLD
            ws[f"{col}{row}"].alignment = CENTER

    footer = 15 + len(results)
    ws.merge_cells(f"A{footer}:O{footer}")
    ws[f"A{footer}"] = FOOTER_TEXT
    ws.row_breaks.append(Break(id=footer))

    ws[f"A{footer + 4}"] = "Additional comments, if any:"
    ws[f"A{footer + 4}"].font = Font(bold=True)
    lines = _comment_lines(group, results)
    for i, line in enumerate(lines or ["None."]):
        row = footer + 5 + i
        ws.merge_cells(f"A{row}:O{row}")
        ws[f"A{row}"] = line
        ws[f"A{row}"].alignment = Alignment(wrap_text=True, vertical="top")

    for row in ws.iter_rows():
        for cell in row:
            font = copy(cell.font)
            font.name = "Calibri"
            font.sz = 18 if cell.row <= 3 else 12
            if cell.coordinate == "C2":
                font.sz, font.b = 14, False
            if 9 <= cell.row <= 12 and cell.column in (14, 15):
                font.color = "000000"
            cell.font = font

    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = 9
    ws.page_margins.left = ws.page_margins.right = 0.25
    ws.page_margins.top = ws.page_margins.bottom = 0.75
    ws.page_margins.header = ws.page_margins.footer = 0.3
    return wb


def _comment_lines(group, results):
    cadets = {r.cadet.id: r.cadet.name for r in results}
    rows = CadetScore.objects.filter(
        score_set__group=group, cadet_id__in=cadets
    ).select_related("score_set__instructor", "score_set__subject")
    by_cadet = {cadet_id: [] for cadet_id in cadets}
    for row in rows:
        comment = row.comment.strip()
        if comment:
            by_cadet[row.cadet_id].append(
                (row.score_set.instructor.display_name, row.score_set.subject.name, comment)
            )
    lines = []
    for cadet_id, name in cadets.items():
        for instructor, subject, comment in sorted(
            by_cadet[cadet_id], key=lambda c: (c[0].casefold(), c[1].casefold())
        ):
            lines.append(f"{name} — {instructor} ({subject}): {comment}")
    return lines
