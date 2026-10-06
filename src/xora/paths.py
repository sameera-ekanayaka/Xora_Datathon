"""Where things live in the repo, so notebooks never hard-code paths."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"
MODELS = REPO_ROOT / "models"
SUBMISSIONS = REPO_ROOT / "submissions"
REPORTS = REPO_ROOT / "reports"


def raw_file(name: str) -> Path:
    """Find a raw data file by name anywhere under data/raw.

    The data zip nests files in folders with spaces in their names
    ("Training Data", "General Data"), so we search instead of spelling them out.
    """
    matches = list(DATA_RAW.rglob(name))
    if not matches:
        raise FileNotFoundError(
            f"{name} not found under {DATA_RAW}. Unzip the data there first."
        )
    if len(matches) > 1:
        raise RuntimeError(f"{name} found more than once: {matches}")
    return matches[0]
