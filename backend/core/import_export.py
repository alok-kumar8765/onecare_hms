import csv
import io
from datetime import datetime
from typing import Optional


def filter_rows_by_period(
    rows: list[dict],
    *,
    date_field: str = "date",
    year: Optional[int] = None,
    month: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Filters records for year/month/date-range exports (previous year, current year, month, or custom range).
    """
    parsed_start = datetime.fromisoformat(start_date).date() if start_date else None
    parsed_end = datetime.fromisoformat(end_date).date() if end_date else None

    filtered = []
    for row in rows:
        raw_val = row.get(date_field)
        if not raw_val:
            continue
        dt = raw_val.date() if isinstance(raw_val, datetime) else (raw_val if hasattr(raw_val, "year") else datetime.fromisoformat(str(raw_val)).date())

        if year is not None and dt.year != year:
            continue
        if month is not None and dt.month != month:
            continue
        if parsed_start is not None and dt < parsed_start:
            continue
        if parsed_end is not None and dt > parsed_end:
            continue
        filtered.append(row)
    return filtered


def export_rows_to_csv(headers: list[str], rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def parse_csv_import(csv_text: str, required_headers: list[str]) -> tuple[list[dict], list[str]]:
    """
    Validates headers and parses CSV rows without mutating database state.
    """
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames or []

    missing = [col for col in required_headers if col not in fieldnames]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return [], errors

    records: list[dict] = []
    for idx, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        records.append({k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()})
    return records, errors