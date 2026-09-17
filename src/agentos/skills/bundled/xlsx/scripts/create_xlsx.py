"""Create a `.xlsx` workbook from a JSON spec.

Spec:
    {
      "sheets": [
        {
          "name": "Sales",
          "rows": [["A", "B"], [1, "=B1*2"]],
          "merged": [{"range": "A1:B1"}],
          "freeze": "A2"
        }
      ]
    }
Entries in "merged" may also be range strings, e.g. "A1:B1", as returned by
inspect_xlsx. Strings and {"range": ...} objects can be mixed in the same list.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook


def _coerce(value: Any) -> Any:
    if isinstance(value, str) and len(value) >= 19 and value[10] == "T":
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def build(spec: dict[str, Any]) -> Workbook:
    wb = Workbook()
    default_sheet = wb.active
    if not isinstance(spec, dict):
        return wb
    sheets = spec.get("sheets") or []
    if not isinstance(sheets, list) or not sheets:
        return wb

    for idx, sheet_spec in enumerate(sheets):
        if not isinstance(sheet_spec, dict):
            continue
        if idx == 0:
            ws = default_sheet
            ws.title = str(sheet_spec.get("name") or "Sheet1")
        else:
            ws = wb.create_sheet(title=str(sheet_spec.get("name") or f"Sheet{idx + 1}"))

        rows = sheet_spec.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, (list, tuple)):
                    ws.append([_coerce(v) for v in row])

        merged_entries = sheet_spec.get("merged")
        if isinstance(merged_entries, list):
            for merged in merged_entries:
                if isinstance(merged, str):
                    ws.merge_cells(merged)
                elif isinstance(merged, dict) and "range" in merged:
                    ws.merge_cells(str(merged["range"]))

        freeze = sheet_spec.get("freeze")
        if isinstance(freeze, str) and freeze:
            ws.freeze_panes = freeze

    return wb


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a .xlsx from a JSON spec.")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.spec.is_file():
        print(f"error: spec {args.spec} not found", file=sys.stderr)
        return 2
    try:
        raw = json.loads(args.spec.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: invalid JSON in {args.spec}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print(f"error: spec must be a JSON object, got {type(raw).__name__}", file=sys.stderr)
        return 2
    try:
        wb = build(raw)
    except Exception as exc:
        print(f"error: failed to build workbook: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(str(args.out))
    except Exception as exc:
        print(f"error: failed to save workbook to {args.out}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
