"""Compact CLI review utility for handbook mining outputs."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable, List, Sequence


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def contains(row: dict, text: str) -> bool:
    text = text.lower().strip()
    if not text:
        return True
    for value in row.values():
        if text in str(value).lower():
            return True
    return False


def row_matches(row: dict, material: str, category: str, keyword: str) -> bool:
    if material and material.lower() not in str(row.get("material", "")).lower():
        return False
    if category and category.lower() not in str(row.get("property_or_data_type", "")).lower() and category.lower() not in str(row.get("category", "")).lower():
        return False
    if keyword and not contains(row, keyword):
        return False
    return True


def sort_rows(rows: List[dict]) -> List[dict]:
    def key(row: dict):
        try:
            confidence = float(row.get("confidence", "0") or 0)
        except ValueError:
            confidence = 0.0
        try:
            page = int(float(row.get("pdf_page", "0") or 0))
        except ValueError:
            page = 0
        return (-confidence, page, row.get("material", ""), row.get("property_name", ""))

    return sorted(rows, key=key)


def format_value(row: dict) -> str:
    value = row.get("value", "")
    units = row.get("units", "")
    if value and units:
        return f"{value} {units}"
    return value or units or ""


def print_rows(rows: Sequence[dict], top: int) -> None:
    if not rows:
        print("No rows matched.")
        return
    sample = rows[0]
    if "current_property" in sample and "comparison_status" in sample:
        print_audit_rows(rows, top)
        return
    headers = [
        ("candidate_id", 28),
        ("material", 18),
        ("property_name", 22),
        ("property_or_data_type", 16),
        ("value", 16),
        ("pdf_page", 8),
        ("printed_page", 8),
        ("data_origin", 24),
        ("confidence", 9),
    ]
    print(" | ".join(title.ljust(width) for title, width in headers))
    print("-" * (sum(width for _, width in headers) + 3 * (len(headers) - 1)))
    for row in rows[:top]:
        value = format_value(row)
        cells = [
            row.get("candidate_id", "")[:28].ljust(28),
            row.get("material", "")[:18].ljust(18),
            row.get("property_name", "")[:22].ljust(22),
            row.get("property_or_data_type", "")[:16].ljust(16),
            value[:16].ljust(16),
            row.get("pdf_page", "")[:8].ljust(8),
            row.get("printed_page", "")[:8].ljust(8),
            row.get("data_origin", "")[:24].ljust(24),
            row.get("confidence", "")[:9].ljust(9),
        ]
        print(" | ".join(cells))
        snippet = row.get("source_text", "")
        if snippet:
            print(f"    {snippet[:220]}")


def print_audit_rows(rows: Sequence[dict], top: int) -> None:
    headers = [
        ("material", 18),
        ("current_property", 18),
        ("current_value", 16),
        ("handbook_candidate", 28),
        ("handbook_condition", 18),
        ("handbook_temperature", 16),
        ("handbook_page", 10),
        ("comparison_status", 30),
    ]
    print(" | ".join(title.ljust(width) for title, width in headers))
    print("-" * (sum(width for _, width in headers) + 3 * (len(headers) - 1)))
    for row in rows[:top]:
        cells = [
            row.get("material", "")[:18].ljust(18),
            row.get("current_property", "")[:18].ljust(18),
            row.get("current_value", "")[:16].ljust(16),
            row.get("handbook_candidate", "")[:28].ljust(28),
            row.get("handbook_condition", "")[:18].ljust(18),
            row.get("handbook_temperature", "")[:16].ljust(16),
            row.get("handbook_page", "")[:10].ljust(10),
            row.get("comparison_status", "")[:30].ljust(30),
        ]
        print(" | ".join(cells))
        notes = row.get("notes", "")
        if notes:
            print(f"    {notes[:220]}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review handbook mining candidates.")
    parser.add_argument("--material", default="", help="Filter by material substring.")
    parser.add_argument("--category", default="", help="Filter by property/category substring.")
    parser.add_argument("--keyword", default="", help="Filter by any substring in the candidate row.")
    parser.add_argument("--top", type=int, default=30, help="Maximum number of rows to print.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Handbook mining output directory.")
    parser.add_argument("--audit", action="store_true", help="Show the audit rows instead of candidate rows.")
    args = parser.parse_args(argv)

    path = args.output_dir / ("fatigue_database_audit.csv" if args.audit else "candidate_data.csv")
    rows = read_rows(path)
    if not rows:
        print(f"No rows found at {path}", file=sys.stderr)
        return 2

    filtered = [row for row in rows if row_matches(row, args.material, args.category, args.keyword)]
    filtered = sort_rows(filtered)
    print(f"Source: {path}")
    print(f"Matched rows: {len(filtered)}")
    print_rows(filtered, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
