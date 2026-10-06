"""Task 2A: forecast daily demand, then add the days up into ISO weeks.

Festivals land in different ISO weeks every year, so a weekly model that
learns "week 16 is big" is wrong as soon as the calendar shifts. A daily model
learns "the days before New Year are big" instead, and the weekly totals
follow the calendar automatically.

Two models are fitted on the same daily panel:
- `TrendRegression`: a readable per-series regression on log volume with a
  growth trend and calendar effects
- `CalendarGBM`: one LightGBM across all series that learns the calendar
  shape on top of the regression's growth trend
"""

import lightgbm as lgb
import numpy as np
import pandas as pd

SEED = 42
SERIES_KEYS = ["depot", "brand", "measure"]
MEASURES = {"total": "total_volume_m3", "chilled": "chilled_volume_m3"}
PRE_FESTIVAL_DAYS = 10
POST_FESTIVAL_DAYS = 4


def calendar_features(calendar: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar day with the festival timing spelled out."""
    cal = calendar.sort_values("date").reset_index(drop=True).copy()
    fest = cal.loc[cal["festival"] != "none", ["date", "festival"]]

    nxt = pd.merge_asof(cal[["date"]], fest.rename(columns={"date": "fest_date"}),
                        left_on="date", right_on="fest_date", direction="forward")
    prv = pd.merge_asof(cal[["date"]], fest.rename(columns={"date": "fest_date"}),
                        left_on="date", right_on="fest_date", direction="backward")
    cal["next_festival"] = nxt["festival"].fillna("none")
    cal["days_to_festival"] = (nxt["fest_date"] - cal["date"]).dt.days.fillna(99).clip(upper=99)
    cal["prev_festival"] = prv["festival"].fillna("none")
    cal["days_since_festival"] = (cal["date"] - prv["fest_date"]).dt.days.fillna(99).clip(upper=99)
    cal["pre_festival"] = cal["days_to_festival"].between(1, PRE_FESTIVAL_DAYS).astype("int8")
    cal["post_festival"] = cal["days_since_festival"].between(1, POST_FESTIVAL_DAYS).astype("int8")
    cal["month"] = cal["date"].dt.month
    cal["day_of_year"] = cal["date"].dt.dayofyear
    cal["t_years"] = (cal["date"] - pd.Timestamp("2024-01-01")).dt.days / 365.25
    return cal


def daily_panel(orders: pd.DataFrame, calendar: pd.DataFrame, uplift: pd.DataFrame = None) -> pd.DataFrame:
    """Daily volume per depot, brand and measure, with zeros on days without orders.

    Every order counts once on its order date, whatever happened to it later.
    `uplift` (depot, brand, iso_year, iso_week, factor_total, factor_chilled)
    scales weeks whose inputs are known to miss some orders.
    """
    o = orders.assign(chilled=np.where(orders["temp_requirement"] == "chilled", orders["order_volume_m3"], 0.0))
    daily = o.groupby(["depot", "brand", "order_date"], observed=True).agg(
        total=("order_volume_m3", "sum"), chilled=("chilled", "sum")).reset_index()

    last_day = orders["order_date"].max()
    cal = calendar_features(calendar)
    days = cal.loc[cal["date"] <= last_day, "date"]
    pairs = daily[["depot", "brand"]].drop_duplicates()
    grid = pairs.merge(days.to_frame(), how="cross")
    daily = grid.merge(daily.rename(columns={"order_date": "date"}), on=["depot", "brand", "date"], how="left").fillna(
        {"total": 0.0, "chilled": 0.0})

    if uplift is not None:
        daily = daily.merge(cal[["date", "iso_year", "iso_week"]], on="date")
        daily = daily.merge(uplift, on=["depot", "brand", "iso_year", "iso_week"], how="left")
        for m in ["total", "chilled"]:
            daily[m] = daily[m] * daily.pop(f"factor_{m}").fillna(1.0)
        daily = daily.drop(columns=["iso_year", "iso_week"])

    long = daily.melt(id_vars=["depot", "brand", "date"], value_vars=["total", "chilled"],
                      var_name="measure", value_name="y")
    # Style and Tech carry no chilled goods, so there is nothing to forecast there
    long = long[(long["measure"] == "total") | (long["brand"] == "Fresh")]
    return long.merge(cal, on="date").sort_values(SERIES_KEYS + ["date"]).reset_index(drop=True)


def future_panel(series: pd.DataFrame, calendar: pd.DataFrame, start, end) -> pd.DataFrame:
    """Rows to forecast: every series on every day from start to end."""
    cal = calendar_features(calendar)
    days = cal[(cal["date"] >= start) & (cal["date"] <= end)]
    return series[SERIES_KEYS].drop_duplicates().merge(days, how="cross")


def _design(df: pd.DataFrame) -> np.ndarray:
    """Columns of the per-series regression: intercept, trend and calendar effects."""
    cols = [np.ones(len(df)), df["t_years"].to_numpy()]
    cols += [(df["dow"] == d).to_numpy(float) for d in range(1, 6)]
    cols += [(df["month"] == m).to_numpy(float) for m in range(2, 13)]
    cols += [df[c].to_numpy(float) for c in ["festival_ramp", "is_payday", "is_holiday", "monsoon",
                                               "pre_festival", "post_festival"]]
    return np.column_stack(cols)


class TrendRegression:
    """Per-series ridge regression on log volume, fitted on operating days only."""

    def __init__(self, ridge: float = 1.0):
        self.ridge = ridge
        self.coef, self.smear = {}, {}

    def fit(self, panel: pd.DataFrame):
        for key, g in panel[panel["is_operating"] == 1].groupby(SERIES_KEYS, observed=True):
            X, y = _design(g), np.log1p(g["y"].to_numpy())
            penalty = self.ridge * np.eye(X.shape[1])
            penalty[:2, :2] = 0  # don't shrink the level or the growth trend
            beta = np.linalg.solve(X.T @ X + penalty, X.T @ y)
            self.coef[key] = beta
            # Undo the bias from averaging in log space
            self.smear[key] = np.mean(np.expm1(y) + 1) / np.mean(np.exp(X @ beta))
        return self

    def trend(self, df: pd.DataFrame) -> np.ndarray:
        """Level and growth only, in log space."""
        out = np.zeros(len(df))
        for key, idx in df.groupby(SERIES_KEYS, observed=True).indices.items():
            b = self.coef[key]
            out[idx] = b[0] + b[1] * df["t_years"].to_numpy()[idx]
        return out

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        out = np.zeros(len(df))
        X = _design(df)
        for key, idx in df.groupby(SERIES_KEYS, observed=True).indices.items():
            out[idx] = (np.exp(X[idx] @ self.coef[key]) * self.smear[key]) - 1
        return np.clip(out, 0, None) * df["is_operating"].to_numpy()


GBM_FEATURES = ["depot", "brand", "measure", "dow", "month", "day_of_year", "is_payday", "is_holiday",
                "monsoon", "festival_ramp", "next_festival", "days_to_festival", "prev_festival",
                "days_since_festival"]
CATEGORICAL = ["depot", "brand", "measure", "next_festival", "prev_festival"]


class CalendarGBM:
    """LightGBM across all series on log volume, with the regression's trend removed."""

    def __init__(self, n_estimators: int = 600):
        self.n_estimators = n_estimators
        self.base = TrendRegression()
        self.model = None
        self.categories = {}

    def _X(self, df):
        X = df[GBM_FEATURES].copy()
        for c in CATEGORICAL:
            X[c] = pd.Categorical(X[c], categories=self.categories[c])
        return X

    def fit(self, panel: pd.DataFrame):
        self.base.fit(panel)
        op = panel[panel["is_operating"] == 1]
        self.categories = {c: sorted(panel[c].unique()) for c in CATEGORICAL}
        target = np.log1p(op["y"].to_numpy()) - self.base.trend(op)
        self.model = lgb.LGBMRegressor(
            n_estimators=self.n_estimators, learning_rate=0.03, num_leaves=31, min_child_samples=20,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1,
        ).fit(self._X(op), target)
        resid = target - self.model.predict(self._X(op))
        self.smear = float(np.mean(np.exp(resid)))
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        log_pred = self.base.trend(df) + self.model.predict(self._X(df))
        out = np.expm1(log_pred) * self.smear
        return np.clip(out, 0, None) * df["is_operating"].to_numpy()


def to_weeks(df: pd.DataFrame, value_cols) -> pd.DataFrame:
    """Add daily values up into ISO weeks per series."""
    return df.groupby(SERIES_KEYS + ["iso_year", "iso_week"], observed=True)[value_cols].sum().reset_index()
