from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook


class RosterError(Exception):
    pass


def cell_text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return " ".join(str(v).split())


def read_sheet(content):
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            rows = workbook.worksheets[0].iter_rows(values_only=True)
            first = next(rows, ())
            headers = [cell_text(v) for v in first]
            width = len(headers)
            data = []
            for row in rows:
                cells = [cell_text(v) for v in row[:width]]
                data.append(cells + [""] * (width - len(cells)))
        finally:
            workbook.close()
    except Exception as exc:
        raise RosterError(str(exc)) from exc
    return headers, data
