"""Lightweight data checks.

Each check returns one row for a summary table, so a notebook can show every
rule, whether it passed and how many rows broke it, instead of failing on the first.
"""

import pandas as pd


def check(name: str, failing_rows: int, total_rows: int, note: str = "") -> dict:
    return {
        "check": name,
        "passed": failing_rows == 0,
        "failing_rows": int(failing_rows),
        "total_rows": int(total_rows),
        "note": note,
    }


def unique_key(df: pd.DataFrame, cols, name: str) -> dict:
    dupes = df.duplicated(subset=cols, keep=False).sum()
    return check(f"{name}: {', '.join(cols) if isinstance(cols, list) else cols} is unique", dupes, len(df))


def no_nulls(df: pd.DataFrame, cols, name: str, note: str = "") -> dict:
    bad = df[cols].isna().any(axis=1).sum()
    return check(f"{name}: no blanks in {', '.join(cols)}", bad, len(df), note)


def in_range(df: pd.DataFrame, col: str, low, high, name: str) -> dict:
    s = df[col]
    bad = (~s.between(low, high)).sum()
    return check(f"{name}: {col} between {low} and {high}", bad, len(df))


def allowed_values(df: pd.DataFrame, col: str, allowed, name: str) -> dict:
    bad = (~df[col].isin(allowed)).sum()
    return check(f"{name}: {col} in {sorted(allowed)}", bad, len(df))


def report(rows) -> pd.DataFrame:
    return pd.DataFrame(rows)
