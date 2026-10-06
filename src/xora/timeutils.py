"""Clock-time helpers. The data stores times as HH:MM strings in Colombo time."""

import pandas as pd


def hhmm_to_minutes(s: pd.Series) -> pd.Series:
    """Convert 'HH:MM' strings to minutes after midnight (float, NaN for blanks)."""
    parts = s.str.split(":", n=1, expand=True)
    return parts[0].astype("float") * 60 + parts[1].astype("float")


def minutes_to_hhmm(m: pd.Series) -> pd.Series:
    """Inverse of hhmm_to_minutes, used when showing results to people."""
    m = m.round().astype("Int64")
    return (m // 60).astype("string").str.zfill(2) + ":" + (m % 60).astype("string").str.zfill(2)
