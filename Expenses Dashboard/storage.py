"""Local data layer for the expenses dashboard.

Everything is stored in plain files next to this script so the whole thing
stays portable and easy to inspect/edit by hand:

  - expenses.csv : one row per expense
  - income.json  : monthly income (default plus per-month overrides)
"""

from __future__ import annotations

import csv
import json
import os
import re
import uuid
from pathlib import Path

import pandas as pd

# Data lives next to this script by default, but EXPENSES_DATA_DIR can point it
# elsewhere — used to keep tests fully isolated from your real files.
BASE_DIR = Path(os.environ.get("EXPENSES_DATA_DIR", Path(__file__).resolve().parent))
EXPENSES_CSV = BASE_DIR / "expenses.csv"
INCOME_JSON = BASE_DIR / "income.json"
FIXED_EXPENSES_JSON = BASE_DIR / "fixed_expenses.json"

CURRENCY = "CHF"

# Money moved into investments is not spending: it gets its own KPI and is
# subtracted from what's left, but kept out of the spending charts.
INVESTMENT_CATEGORY = "Investment"

# Sensible default categories for day-to-day life in Geneva.
DEFAULT_CATEGORIES = [
    "Rent",
    "Groceries",
    "Restaurants",
    "Transport",
    "Health & Insurance",
    "Utilities",
    "Shopping",
    "Leisure",
    "Travel",
    INVESTMENT_CATEGORY,
    "Other",
]

# Date ranges are optional; blank dates mean the expense is counted in the
# salary cycle in which it was paid.
EXPENSE_COLUMNS = [
    "date", "amount", "category", "description", "spread_start", "spread_end",
]
def load_fixed_expenses() -> list[dict]:
    """Load recurring monthly expense templates."""
    if not FIXED_EXPENSES_JSON.exists():
        return []
    try:
        data = json.loads(FIXED_EXPENSES_JSON.read_text())
        if not isinstance(data, list):
            return []
        cleaned = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                cleaned.append({
                    "id": str(item.get("id") or uuid.uuid4().hex),
                    "start_date": pd.Timestamp(item["start_date"]).strftime("%Y-%m-%d"),
                    "day": max(1, min(31, int(item["day"]))),
                    "amount": round(float(item["amount"]), 2),
                    "category": str(item.get("category") or "Other").strip() or "Other",
                    "description": str(item.get("description") or "").strip(),
                    "generated": [str(x) for x in item.get("generated", [])],
                })
            except (KeyError, TypeError, ValueError):
                continue
        return cleaned
    except (json.JSONDecodeError, OSError, AttributeError):
        return []


def save_fixed_expenses(items: list[dict]) -> None:
    """Persist recurring monthly expense templates."""
    clean = []
    for item in items:
        clean.append({
            "id": str(item["id"]),
            "start_date": pd.Timestamp(item["start_date"]).strftime("%Y-%m-%d"),
            "day": max(1, min(31, int(item["day"]))),
            "amount": round(float(item["amount"]), 2),
            "category": str(item.get("category") or "Other").strip() or "Other",
            "description": str(item.get("description") or "").strip(),
            "generated": sorted(set(str(x) for x in item.get("generated", []))),
        })
    FIXED_EXPENSES_JSON.write_text(
        json.dumps(clean, indent=2, ensure_ascii=False)
    )


def add_fixed_expense(date, amount: float, category: str, description: str) -> dict:
    """Create a recurring monthly expense template and return it."""
    start = pd.Timestamp(date).normalize()
    item = {
        "id": uuid.uuid4().hex,
        "start_date": start.strftime("%Y-%m-%d"),
        "day": int(start.day),
        "amount": round(float(amount), 2),
        "category": str(category),
        "description": (description or "").strip(),
        "generated": [],
    }
    items = load_fixed_expenses()
    items.append(item)
    save_fixed_expenses(items)
    return item


def delete_fixed_expense(fixed_id: str) -> bool:
    """Delete a recurring template. Existing generated expenses are kept."""
    items = load_fixed_expenses()
    remaining = [item for item in items if item["id"] != str(fixed_id)]
    if len(remaining) == len(items):
        return False
    save_fixed_expenses(remaining)
    return True


def _fixed_occurrence_date(year: int, month: int, day: int) -> pd.Timestamp:
    period = pd.Period(f"{year:04d}-{month:02d}", freq="M")
    return period.to_timestamp() + pd.Timedelta(days=min(day, period.days_in_month) - 1)


def generate_fixed_expenses(until_date=None) -> int:
    """Generate missing monthly occurrences up to ``until_date``.

    Generated rows use the normal expenses.csv schema, so the iPhone Shortcut
    and existing expense editor continue to work unchanged. A separate
    occurrence key in fixed_expenses.json prevents duplicate generation.
    """
    until = pd.Timestamp(until_date or pd.Timestamp.today()).normalize()
    items = load_fixed_expenses()
    if not items:
        return 0

    new_rows = []
    changed = False

    for item in items:
        start = pd.Timestamp(item["start_date"]).normalize()
        first_period = start.to_period("M")
        last_period = until.to_period("M")
        if first_period > last_period:
            continue

        generated = set(item.get("generated", []))
        period = first_period
        while period <= last_period:
            occurrence = _fixed_occurrence_date(
                period.year, period.month, item["day"]
            )
            key = str(period)
            if occurrence >= start and occurrence <= until and key not in generated:
                new_rows.append({
                    "date": occurrence.strftime("%Y-%m-%d"),
                    "amount": item["amount"],
                    "category": item["category"],
                    "description": item["description"],
                })
                generated.add(key)
                changed = True
            period += 1

        item["generated"] = sorted(generated)

    if new_rows:
        rows = pd.DataFrame(new_rows, columns=EXPENSE_COLUMNS)
        _append_expense_rows(rows)

    if changed:
        save_fixed_expenses(items)

    return len(new_rows)


def load_expenses() -> pd.DataFrame:
    """Return all expenses as a typed DataFrame (empty frame if no file yet)."""
    if not EXPENSES_CSV.exists():
        return _empty_expenses()

    # Use csv.reader so malformed rows cannot silently shift columns. This also
    # lets us recover old appends that were joined to the preceding row when
    # the CSV lacked a final newline.
    with EXPENSES_CSV.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.reader(csv_file)
        columns = next(reader)
        expected = len(columns)

        def recover(fields):
            if len(fields) == expected:
                return [fields]

            if expected == len(EXPENSE_COLUMNS) and len(fields) > expected:
                boundary = expected - 1
                if len(fields) > boundary + 2:
                    joined_dates = re.fullmatch(
                        r"(\d{4}-\d{2}-\d{2})(\d{4}-\d{2}-\d{2})",
                        fields[boundary],
                    )
                    if joined_dates:
                        previous = fields[:boundary] + [joined_dates.group(1)]
                        following = [joined_dates.group(2)] + fields[boundary + 1:]
                        if len(previous) == expected and len(following) >= expected:
                            return recover(previous) + recover(following)

                    next_date = pd.to_datetime(fields[boundary], errors="coerce")
                    next_amount = pd.to_numeric(
                        fields[boundary + 1], errors="coerce"
                    )
                    if pd.notna(next_date) and pd.notna(next_amount):
                        previous = fields[:boundary] + [""]
                        following = fields[boundary:]
                        if len(following) >= expected:
                            return recover(previous) + recover(following)

                # A description with unquoted commas occupies the middle fields.
                return [
                    fields[:3] + [",".join(fields[3:-2]), fields[-2], fields[-1]]
                ]

            return [fields + [""] * (expected - len(fields))]

        recovered_rows = [row for fields in reader for row in recover(fields)]
    df = pd.DataFrame(recovered_rows, columns=columns)
    # Be forgiving about a hand-edited file that is missing columns.
    for col in EXPENSE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[EXPENSE_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["category"] = df["category"].fillna("Other").astype(str).str.strip()
    df.loc[df["category"] == "", "category"] = "Other"  # blank/whitespace -> Other
    df["description"] = df["description"].fillna("").astype(str)
    for col in ("spread_start", "spread_end"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df = df.dropna(subset=["date", "amount"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def _empty_expenses() -> pd.DataFrame:
    df = pd.DataFrame(columns=EXPENSE_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = pd.to_numeric(df["amount"])
    df["spread_start"] = pd.to_datetime(pd.Series(dtype="datetime64[ns]"))
    df["spread_end"] = pd.to_datetime(pd.Series(dtype="datetime64[ns]"))
    df["month"] = pd.Series(dtype="str")
    return df


def salary_date_for_month(month: str, salary_dates: dict[str, str] | None = None) -> pd.Timestamp:
    """Return a month's configured salary date, defaulting to its 23rd."""
    period = pd.Period(month, freq="M")
    default = period.to_timestamp() + pd.Timedelta(days=22)
    configured = (salary_dates or {}).get(str(period))
    if not configured:
        return default
    date = pd.to_datetime(configured, errors="coerce")
    if pd.isna(date) or date.to_period("M") != period:
        return default
    return pd.Timestamp(date).normalize()


def salary_cycle_start(value, salary_dates: dict[str, str] | None = None) -> pd.Timestamp:
    """Return the salary date on which the cycle containing ``value`` began."""
    date = pd.Timestamp(value)
    current_month = date.to_period("M")
    current_salary = salary_date_for_month(str(current_month), salary_dates)
    if date.normalize() < current_salary:
        return salary_date_for_month(str(current_month - 1), salary_dates)
    return current_salary


def salary_cycle_label(start, salary_dates: dict[str, str] | None = None) -> str:
    """Return a readable label ending one day before the following salary date."""
    cycle_start = pd.Timestamp(start).normalize()
    following_month = cycle_start.to_period("M") + 1
    cycle_end = salary_date_for_month(str(following_month), salary_dates) - pd.Timedelta(days=1)
    return f"{cycle_start:%Y-%m-%d} to {cycle_end:%Y-%m-%d}"


def add_salary_cycles(df: pd.DataFrame,
                      salary_dates: dict[str, str] | None = None) -> pd.DataFrame:
    """Add derived salary-cycle fields without changing stored expense records.

    Each cycle uses the month's configured salary date, or the 23rd by default.
    ``salary_income_month`` identifies the existing monthly income setting used
    for that cycle: the month in which its salary is received.
    """
    out = df.copy()
    if out.empty:
        out["salary_cycle_start"] = pd.Series(dtype="datetime64[ns]")
        out["salary_cycle"] = pd.Series(dtype="str")
        out["salary_income_month"] = pd.Series(dtype="str")
        return out

    starts = out["date"].apply(lambda date: salary_cycle_start(date, salary_dates))
    out["salary_cycle_start"] = starts
    out["salary_cycle"] = starts.map(lambda start: salary_cycle_label(start, salary_dates))
    out["salary_income_month"] = starts.dt.to_period("M").astype(str)
    return out


def amortize(df: pd.DataFrame,
             salary_dates: dict[str, str] | None = None) -> pd.DataFrame:
    """Spread expenses with date ranges evenly across overlapping salary cycles."""
    if df.empty:
        return df.copy()

    out = []
    for _, r in df.iterrows():
        range_start = pd.to_datetime(r.get("spread_start"), errors="coerce")
        range_end = pd.to_datetime(r.get("spread_end"), errors="coerce")
        if pd.notna(range_start) and pd.notna(range_end):
            cursor = salary_cycle_start(range_start, salary_dates)
            allocations = []
            while cursor <= range_end:
                following = salary_date_for_month(
                    str(cursor.to_period("M") + 1), salary_dates
                )
                cycle_end = following - pd.Timedelta(days=1)
                overlap_start = max(cursor, range_start.normalize())
                overlap_end = min(cycle_end, range_end.normalize())
                if overlap_start <= overlap_end:
                    allocations.append(cursor)
                cursor = following

            if allocations:
                share = round(float(r["amount"]) / len(allocations), 2)
                allocated = 0.0
                for index, cycle_start in enumerate(allocations):
                    amount = (
                        round(float(r["amount"]) - allocated, 2)
                        if index == len(allocations) - 1 else share
                    )
                    allocated += amount
                    out.append({
                        "date": cycle_start,
                        "amount": amount,
                        "category": r["category"],
                        "description": r["description"],
                        "spread_start": range_start,
                        "spread_end": range_end,
                        "month": str(cycle_start.to_period("M")),
                    })
                continue

        paid_date = pd.Timestamp(r["date"])
        out.append({
            "date": paid_date,
            "amount": float(r["amount"]),
            "category": r["category"],
            "description": r["description"],
            "spread_start": range_start if pd.notna(range_start) else pd.NaT,
            "spread_end": range_end if pd.notna(range_end) else pd.NaT,
            "month": str(paid_date.to_period("M")),
        })

    result = pd.DataFrame(out)
    return result.sort_values("date", ascending=False).reset_index(drop=True)


def add_expense(date, amount: float, category: str, description: str,
                spread_start=None, spread_end=None) -> None:
    """Append a single expense to the CSV, creating it on first use."""
    row = pd.DataFrame(
        [{
            "date": pd.to_datetime(date).strftime("%Y-%m-%d"),
            "amount": round(float(amount), 2),
            "category": category,
            "description": (description or "").strip(),
            "spread_start": pd.to_datetime(spread_start).strftime("%Y-%m-%d")
            if spread_start else "",
            "spread_end": pd.to_datetime(spread_end).strftime("%Y-%m-%d")
            if spread_end else "",
        }]
    )
    _append_expense_rows(row)


def add_expenses(df: pd.DataFrame) -> int:
    """Append many expenses at once (used by CSV import). Returns rows added."""
    rows = df.copy()
    for col in EXPENSE_COLUMNS:
        if col not in rows.columns:
            rows[col] = pd.NA
    rows = rows[EXPENSE_COLUMNS].copy()
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["amount"] = pd.to_numeric(rows["amount"], errors="coerce")
    rows = rows.dropna(subset=["date", "amount"])
    if rows.empty:
        return 0

    rows["date"] = rows["date"].dt.strftime("%Y-%m-%d")
    rows["amount"] = rows["amount"].round(2)
    rows["category"] = rows["category"].fillna("Other").astype(str)
    rows["description"] = rows["description"].fillna("").astype(str)
    for col in ("spread_start", "spread_end"):
        rows[col] = pd.to_datetime(rows[col], errors="coerce").dt.strftime("%Y-%m-%d")

    _append_expense_rows(rows)
    return len(rows)


def overwrite_expenses(df: pd.DataFrame) -> int:
    """Persist a full DataFrame back to disk (used by the edit table).

    Coerces types and drops rows with an invalid date or amount so a blank or
    half-filled row from the editor never corrupts the file. Returns the number
    of rows written.
    """
    out = df.copy()
    for col in EXPENSE_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    out = out.dropna(subset=["date", "amount"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out["amount"] = out["amount"].round(2)
    out["category"] = out["category"].fillna("Other").astype(str)
    out["description"] = out["description"].fillna("").astype(str)
    for col in ("spread_start", "spread_end"):
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
    out[EXPENSE_COLUMNS].to_csv(EXPENSES_CSV, index=False)
    return len(out)


def _append_expense_rows(rows: pd.DataFrame) -> None:
    """Append rows, migrating older/missing CSV columns to the current schema."""
    rows = rows[EXPENSE_COLUMNS].copy()
    if EXPENSES_CSV.exists():
        try:
            current_columns = pd.read_csv(EXPENSES_CSV, nrows=0).columns.tolist()
        except (OSError, pd.errors.ParserError):
            current_columns = []
        if current_columns != EXPENSE_COLUMNS:
            existing = load_expenses()[EXPENSE_COLUMNS]
            overwrite_expenses(pd.concat([existing, rows], ignore_index=True))
            return

    header = not EXPENSES_CSV.exists()
    if not header and EXPENSES_CSV.stat().st_size:
        with EXPENSES_CSV.open("rb") as existing_file:
            existing_file.seek(-1, os.SEEK_END)
            needs_separator = existing_file.read(1) not in (b"\n", b"\r")
        if needs_separator:
            with EXPENSES_CSV.open("ab") as existing_file:
                existing_file.write(b"\n")
    rows.to_csv(EXPENSES_CSV, mode="a", header=header, index=False)


def load_income() -> dict:
    """Return monthly income settings and optional salary-date overrides.

    Income is assumed constant month to month (``default``); individual months
    can override it (e.g. a bonus month) without touching the default.
    """
    base = {"default": 0.0, "overrides": {}, "salary_dates": {}, "salary_start_date": None}
    if not INCOME_JSON.exists():
        return base
    try:
        data = json.loads(INCOME_JSON.read_text())
        base["default"] = float(data.get("default", 0.0))
        base["overrides"] = {
            str(k): float(v) for k, v in data.get("overrides", {}).items()
        }
        base["salary_dates"] = {
            str(k): str(v) for k, v in data.get("salary_dates", {}).items()
        }
        if data.get("salary_start_date"):
            base["salary_start_date"] = str(data["salary_start_date"])
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass
    return base


def save_income(default: float, overrides: dict[str, float],
                salary_dates: dict[str, str] | None = None,
                salary_start_date: str | None = None) -> None:
    clean_overrides = {k: round(float(v), 2) for k, v in overrides.items()}
    clean_salary_dates = {
        str(month): salary_date_for_month(str(month), {str(month): str(date)}).strftime("%Y-%m-%d")
        for month, date in (salary_dates or {}).items()
        if pd.notna(pd.to_datetime(date, errors="coerce"))
        and pd.Timestamp(pd.to_datetime(date)).to_period("M") == pd.Period(month, freq="M")
    }
    existing_start_date = None
    try:
        if INCOME_JSON.exists():
            existing = json.loads(INCOME_JSON.read_text())
            existing_start_date = existing.get("salary_start_date")
    except (json.JSONDecodeError, OSError, AttributeError):
        existing_start_date = None

    payload = {
        "default": round(float(default), 2),
        "overrides": clean_overrides,
        "salary_dates": clean_salary_dates,
    }
    effective_start_date = salary_start_date or existing_start_date
    if effective_start_date:
        payload["salary_start_date"] = str(effective_start_date)

    INCOME_JSON.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )
    )


def income_for_month(month: str) -> float:
    """Income for a given "YYYY-MM" month: its override, else the default."""
    data = load_income()
    return float(data["overrides"].get(month, data["default"]))


def all_categories(df: pd.DataFrame) -> list[str]:
    """Default categories plus any extra ones already present in the data."""
    seen = list(DEFAULT_CATEGORIES)
    for cat in df["category"].dropna().unique():
        if cat not in seen:
            seen.append(str(cat))
    return seen
