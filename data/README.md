# Data folder

Nothing in here is committed. To set it up:

1. Unzip the data so its four folders sit inside `data/raw/`:

```
data/raw/
├── General Data/
├── Submission Templates/
├── Test Data/
└── Training Data/
```

2. Run the notebooks in order. They write their intermediate tables to `data/processed/`.

The helpers in `src/xora/paths.py` find raw files by name, so the exact nesting inside `data/raw/` does not matter.
