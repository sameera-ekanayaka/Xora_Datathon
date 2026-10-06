"""Loading raw files and saving the tables passed between notebooks."""

import pandas as pd

from .paths import DATA_PROCESSED, raw_file


def load_raw(name: str, **kwargs) -> pd.DataFrame:
    """Read one raw CSV by file name."""
    return pd.read_csv(raw_file(name), **kwargs)


def save_processed(df: pd.DataFrame, name: str) -> None:
    """Save a table for the next notebook. Parquet keeps dtypes, CSV would not."""
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATA_PROCESSED / f"{name}.parquet", index=False)


def load_processed(name: str) -> pd.DataFrame:
    path = DATA_PROCESSED / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run the earlier notebook that writes it.")
    return pd.read_parquet(path)
