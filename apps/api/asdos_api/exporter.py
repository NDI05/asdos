from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import xlsxwriter

MAX_CELL_CHARS = 32767
MAX_ROWS_PER_SHEET = 1_048_576


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return (slug or "assessment")[:48]


def _split_text(value: str) -> list[str]:
    # split at a code point boundary; never truncate long source text.
    return [value[pos:pos + 30000] for pos in range(0, len(value), 30000)] or [""]


def workbook_filename(title: str, mode: str, created_at: datetime | None = None) -> str:
    stamp = (created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"ASDOS_{_slug(title)}_{mode}_{stamp}.xlsx"


def build_workbook(payload: dict[str, Any]) -> bytes:
    overflow_rows: list[list[Any]] = []
    output = io.BytesIO()
    book = xlsxwriter.Workbook(output, {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
        "strings_to_numbers": False,
        "default_date_format": "yyyy-mm-dd hh:mm:ss",
    })
    book.set_properties({"title": f"ASDOS {payload['assessment']['title']}", "subject": "Export snapshot", "author": "ASDOS"})
    header_fmt = book.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#174C46", "text_wrap": True, "valign": "top", "border": 1})
    title_fmt = book.add_format({"bold": True, "font_size": 16, "font_color": "#174C46"})
    key_fmt = book.add_format({"bold": True, "bg_color": "#EAF1EF", "text_wrap": True})
    text_fmt = book.add_format({"text_wrap": True, "valign": "top"})
    number_fmt = book.add_format({"num_format": "0.00"})
    integer_fmt = book.add_format({"num_format": "0"})
    info = payload["info"]
    info_sheet = book.add_worksheet("Informasi")
    info_sheet.set_column("A:A", 28)
    info_sheet.set_column("B:B", 90)
    info_sheet.write(0, 0, "ASDOS — DRAFT, BELUM DISAHKAN" if payload["mode"] == "draft" else "ASDOS — NILAI FINAL", title_fmt)
    info_sheet.write_row(2, 0, ["Kunci", "Nilai"], header_fmt)
    for row_idx, (key, value) in enumerate(info.items(), start=3):
        info_sheet.write_string(row_idx, 0, str(key), key_fmt)
        info_sheet.write_string(row_idx, 1, str(value), text_fmt)
    info_sheet.freeze_panes(3, 0)

    question_headers = [f"{question['label']}_Kontribusi" for question in payload["questions"]]
    summary_headers = ["submission_id", "NIM", "Nama", "Attempt", *question_headers, "Total_Kontribusi", "Nilai_Akhir", "Status", "Snapshot_ID"]
    write_table(book, "Rekap_Nilai", summary_headers, payload["summary"], header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    write_table(book, "Detail_Nomor", ["submission_id", "NIM", "question_id", "Nomor", "Raw", "Max_Raw", "Bobot", "Kontribusi", "Status_Jawaban", "Sumber_Nilai", "Review_Status", "Alasan_Override", "Revision_ID"], payload["question_details"], header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    write_table(book, "Detail_Kriteria", ["submission_id", "question_id", "criterion_id", "Kredit", "Max_Poin", "Poin", "Evidence_Refs", "Alasan", "Source"], payload["criterion_details"], header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    write_table(book, "Transkripsi", ["submission_id", "question_id", "segment_id", "region_id", "Halaman", "Urutan", "Teks", "Flags", "Transcript_Revision_ID"], payload["transcriptions"], header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    write_table(book, "Rubrik", ["assessment_revision_id", "question_id", "Nomor", "Soal", "Bobot", "Max_Raw", "criterion_id", "Deskripsi", "Max_Poin", "Level_dan_Anchor", "Kunci", "Alternatif"], payload["rubric"], header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    write_table(book, "Riwayat", ["event_id", "resource_id", "action", "actor_display", "waktu", "previous_revision", "new_revision", "reason"], payload["history"], header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    write_table(book, "Metadata", ["Key", "Value"], list(payload["metadata"].items()), header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    if overflow_rows:
        write_table(book, "Teks_Lanjutan", ["Sheet", "Baris", "Kolom", "Bagian", "Jumlah_Bagian", "Teks"], overflow_rows, header_fmt, text_fmt, number_fmt, integer_fmt, overflow_rows)
    book.close()
    return output.getvalue()


def write_table(book, name, headers, rows, header_fmt, text_fmt, number_fmt, integer_fmt,
                overflow_rows: list[list[Any]]):
    base_widths = [min(48, max(12, min(len(str(header)) + 2, 32))) for header in headers]
    sheet_index = 1
    sheet = None
    sheet_row = 0

    def new_sheet(part: int):
        worksheet = book.add_worksheet(name if part == 1 else f"{name[:26]}_{part}")
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, 0, len(headers) - 1)
        for column, width in enumerate(base_widths):
            worksheet.set_column(column, column, width, text_fmt)
        worksheet.write_row(0, 0, headers, header_fmt)
        return worksheet

    sheet = new_sheet(sheet_index)
    sheet_row = 1
    numeric_headers = {"Raw", "Max_Raw", "Bobot", "Kontribusi", "Kredit", "Max_Poin", "Poin", "Total_Kontribusi", "Nilai_Akhir", "Attempt", "Halaman", "Urutan"}
    for data_row in rows:
        if sheet_row >= MAX_ROWS_PER_SHEET:
            sheet_index += 1
            sheet = new_sheet(sheet_index)
            sheet_row = 1
        for column, raw_value in enumerate(data_row):
            value = raw_value
            if value is None:
                continue
            if isinstance(value, bool):
                sheet.write_boolean(sheet_row, column, value)
            elif isinstance(value, int):
                sheet.write_number(sheet_row, column, value, integer_fmt)
            elif isinstance(value, (Decimal, float)):
                sheet.write_number(sheet_row, column, float(value), number_fmt)
            elif isinstance(value, str):
                if headers[column] in numeric_headers:
                    try:
                        numeric_value = Decimal(value)
                    except Exception:
                        numeric_value = None
                    if numeric_value is not None and numeric_value.is_finite():
                        sheet.write_number(sheet_row, column, float(numeric_value), integer_fmt if headers[column] in {"Attempt", "Halaman", "Urutan"} else number_fmt)
                        continue
                if len(value) > MAX_CELL_CHARS:
                    parts = _split_text(value)
                    col_name = str(headers[column])
                    for part_no, part in enumerate(parts, start=1):
                        overflow_rows.append([name, sheet_row + 1, col_name, part_no, len(parts), part])
                    sheet.write_string(sheet_row, column, "[teks lengkap di sheet Teks_Lanjutan]", text_fmt)
                else:
                    sheet.write_string(sheet_row, column, value, text_fmt)
            else:
                serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                if len(serialized) > MAX_CELL_CHARS:
                    parts = _split_text(serialized)
                    for part_no, part in enumerate(parts, start=1):
                        overflow_rows.append([name, sheet_row + 1, str(headers[column]), part_no, len(parts), part])
                    sheet.write_string(sheet_row, column, "[teks lengkap di sheet Teks_Lanjutan]", text_fmt)
                else:
                    sheet.write_string(sheet_row, column, serialized, text_fmt)
        sheet_row += 1
    sheet.autofilter(0, 0, max(0, sheet_row - 1), len(headers) - 1)
