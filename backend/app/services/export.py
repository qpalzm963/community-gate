"""進出紀錄匯出：CSV（UTF-8 BOM，Excel 可直接開啟中文）與 XLSX。"""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .labels import CATEGORY, DECISION, DIRECTION, VEHICLE_TYPE

COLUMNS = [
    ("occurred_at", "時間", 20),
    ("lane_name", "車道", 12),
    ("direction", "方向", 8),
    ("plate_display", "車牌", 12),
    ("vehicle_type", "車種", 8),
    ("category", "類別", 10),
    ("decision", "處理結果", 12),
    ("household_unit", "戶別", 14),
    ("confidence", "信心值", 8),
    ("operator_name", "操作人員", 12),
    ("note", "備註", 30),
]


def _row(ev: dict) -> list:
    occurred = ev["occurred_at"]
    return [
        occurred.strftime("%Y-%m-%d %H:%M:%S") if hasattr(occurred, "strftime") else str(occurred),
        ev["lane_name"],
        DIRECTION.get(ev["direction"], ev["direction"]),
        ev["plate_display"],
        VEHICLE_TYPE.get(ev["vehicle_type"], ev["vehicle_type"]),
        CATEGORY.get(ev["category"], ev["category"]),
        DECISION.get(ev["decision"], ev["decision"]),
        ev["household_unit"],
        round(ev["confidence"] or 0, 3),
        ev["operator_name"],
        ev["note"],
    ]


def to_csv(events: Iterable[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c[1] for c in COLUMNS])
    for ev in events:
        w.writerow(_row(ev))
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def to_xlsx(events: Iterable[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "進出紀錄"
    ws.append([c[1] for c in COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F5597")
    for ev in events:
        ws.append(_row(ev))
    for i, (_k, _t, width) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
