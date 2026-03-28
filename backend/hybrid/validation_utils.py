"""
hybrid/validation_utils.py
---------------------------
Generic evidence parsing and metric grounding utilities.
Used by both the original hybrid pipeline and the new hybrid_crew pipeline.

Functions:
  parse_evidence(text)             -> list[dict]
    Parses a delimited text block (space/tab/pipe) into a list of row dicts.

  metric_value_grounded(col, val, rows) -> bool
    Returns True if (col, val) appears as a verbatim pair in any row of the evidence.

  numeric_grounded(val, text)       -> bool
    Fallback: returns True if val appears anywhere in the evidence text.
"""

import re
import csv
import io
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def parse_evidence(text: str) -> List[Dict[str, str]]:
    """
    Parse a text block into a list of row dicts.

    Supports:
      - Pipe-delimited (|) tables (SQL-style output)
      - Tab-delimited tables
      - Space-delimited tables (two or more spaces as separator)
      - Fallback: return [] if no structured data found

    Example pipe-delimited input:
      author | final_influence_score
      userA  | 42.5
      userB  | 31.0

    Example space-delimited input:
      author  final_influence_score
      userA   42.5
      userB   31.0
    """
    if not text or not text.strip():
        return []

    lines = [l for l in text.splitlines() if l.strip()]

    # ── Auto-detect delimiter ────────────────────────────────────────────────
    # Priority: pipe → tab → multi-space

    # 1. Pipe-delimited
    if any("|" in l for l in lines[:3]):
        data_lines = [l for l in lines if "|" in l and not re.match(r"^\s*[-|+]+\s*$", l)]
        if len(data_lines) < 2:
            return []
        reader = _parse_delimited(data_lines, delimiter="|")
        if reader:
            return reader

    # 2. Tab-delimited
    if any("\t" in l for l in lines[:3]):
        reader = _parse_delimited(lines, delimiter="\t")
        if reader:
            return reader

    # 3. Multi-space (≥2 spaces as separator)
    if len(lines) >= 2:
        try:
            headers = re.split(r"  +", lines[0].strip())
            if len(headers) >= 2:
                rows = []
                for line in lines[1:]:
                    values = re.split(r"  +", line.strip())
                    if len(values) == len(headers):
                        rows.append(dict(zip(
                            [h.strip() for h in headers],
                            [v.strip() for v in values]
                        )))
                if rows:
                    return rows
        except Exception as exc:
            logger.debug(f"[parse_evidence] Multi-space parse failed: {exc}")

    return []


def _parse_delimited(lines: list, delimiter: str) -> List[Dict[str, str]]:
    """Parse lines with a given delimiter into list of row dicts."""
    try:
        cleaned = "\n".join(lines)
        reader = csv.DictReader(io.StringIO(cleaned), delimiter=delimiter)
        rows = []
        for row in reader:
            # Strip whitespace from keys and values
            clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
            if clean_row:
                rows.append(clean_row)
        return rows
    except Exception as exc:
        logger.debug(f"[_parse_delimited] Failed with delimiter='{delimiter}': {exc}")
        return []


def metric_value_grounded(col: str, val: str, rows: List[Dict[str, str]]) -> bool:
    """
    Check if (col=val) appears as a verbatim combination in any row of the evidence.

    This is the strict metric-aware grounding check. A value must appear
    in the SAME ROW as the column name, not just anywhere in the text.
    """
    val_clean = val.replace(",", "").strip()
    for row in rows:
        row_val = row.get(col, "").replace(",", "").strip()
        if row_val and row_val == val_clean:
            return True
    return False


def numeric_grounded(val: str, text: str) -> bool:
    """
    Fallback check: does val appear anywhere as a number in the evidence text?
    Used when metric_value_grounded cannot be applied (e.g., non-tabular evidence).
    """
    val_clean = re.escape(val.replace(",", "").strip())
    return bool(re.search(rf"\b{val_clean}\b", text))
