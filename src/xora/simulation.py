"""Route simulation for Task 1.

Three small models describe one stop at a time:
- how late the vehicle leaves the depot
- how much slower than planned each leg drives
- how long the handling takes at each outlet

The simulator then replays every drafted route many times, stop by stop, with
the same timing rules the real routes follow:

    depart(first leg) = planned depart + depot delay
    arrival           = depart + travel
    service starts    = max(arrival, window open)
    depart(next leg)  = service start + service time

P(late) for a stop is the share of runs where it arrives after the window
closes. Because lateness is built from the service and travel predictions,
the two Task 1 outputs cannot contradict each other.
"""

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

SEED = 42

CATEGORICAL = ["brand", "depot", "district", "temp_requirement", "dock_type",
               "parking_constraint", "vehicle_type", "vehicle_temp", "outlet_id"]

TRAVEL_FEATURES = [
    "district", "depot", "brand", "vehicle_type", "seq", "is_first_stop", "leg_distance_km",
    "planned_travel_min", "planned_hour", "minutes_into_route", "dow", "month", "monsoon",
    "is_payday", "is_holiday", "festival_ramp", "is_festival_day", "days_to_festival",
    "disruption_index", "speed_index", "district_hist_travel_ratio",
]

DELAY_FEATURES = [
    "depot", "brand", "vehicle_type", "vehicle_temp", "route_start_min", "route_n_stops",
    "route_volume_m3", "route_weight_kg", "load_share_volume", "dow", "month", "monsoon",
    "is_payday", "festival_ramp", "days_to_festival", "vehicle_hist_depart_delay",
]

LGB_PARAMS = dict(
    learning_rate=0.03, num_leaves=63, min_child_samples=40, subsample=0.8, subsample_freq=1,
    colsample_bytree=0.8, reg_lambda=1.0, random_state=SEED, verbose=-1, n_jobs=4,
)


def _fit_lgb(X, y, X_val, y_val, **params):
    """Fit with early stopping on a later time window and return the model."""
    model = lgb.LGBMRegressor(n_estimators=4000, **{**LGB_PARAMS, **params})
    model.fit(X, y, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(200, verbose=False)])
    return model


def _refit(model, X, y):
    """Refit on more data with the number of trees found by early stopping."""
    params = model.get_params()
    params["n_estimators"] = max(int(model.best_iteration_ * 1.1), 50)
    return lgb.LGBMRegressor(**params).fit(X, y)


@dataclass
class RouteSimulator:
    service_features: list
    travel_features: list = field(default_factory=lambda: list(TRAVEL_FEATURES))
    delay_features: list = field(default_factory=lambda: list(DELAY_FEATURES))
    service_objective: str = "mean"
    huber_delta: float = 5.0
    n_sims: int = 1000
    seed: int = SEED
    service_model: object = None
    travel_model: object = None
    delay_model: object = None
    pools: dict = field(default_factory=dict)

    # ---------- fitting ----------
    def _service_params(self):
        if self.service_objective == "huber":
            return dict(objective="huber", alpha=self.huber_delta)
        return dict(objective={"median": "l1", "mean": "l2"}[self.service_objective])

    @staticmethod
    def _travel_target(df):
        return np.log(df["actual_travel_duration_min"] / df["planned_travel_min"].clip(lower=1))

    @staticmethod
    def _first_legs(df):
        return df[df["seq"] == 0]

    @staticmethod
    def _delay_target(df):
        return df["actual_depart_time_min"] - df["planned_depart_time_min"]

    def fit(self, fit_df: pd.DataFrame, val_df: pd.DataFrame):
        """Fit the three components on `fit_df`, stopping early on the later `val_df`."""
        sp = self._service_params()
        self.service_model = _fit_lgb(fit_df[self.service_features], fit_df["service_min"],
                                      val_df[self.service_features], val_df["service_min"], **sp)
        self.travel_model = _fit_lgb(fit_df[self.travel_features], self._travel_target(fit_df),
                                     val_df[self.travel_features], self._travel_target(val_df))
        f1, v1 = self._first_legs(fit_df), self._first_legs(val_df)
        self.delay_model = _fit_lgb(f1[self.delay_features], self._delay_target(f1),
                                    v1[self.delay_features], self._delay_target(v1),
                                    num_leaves=15, min_child_samples=100)
        return self

    def refit(self, df: pd.DataFrame):
        """Refit all components on `df` with the tree counts already chosen."""
        self.service_model = _refit(self.service_model, df[self.service_features], df["service_min"])
        self.travel_model = _refit(self.travel_model, df[self.travel_features], self._travel_target(df))
        f1 = self._first_legs(df)
        self.delay_model = _refit(self.delay_model, f1[self.delay_features], self._delay_target(f1))
        return self

    def learn_noise(self, df: pd.DataFrame):
        """Store out-of-time residuals that the simulation samples from.

        `df` must be a window the models were not trained on, so the noise is
        honest. Travel noise is split into a shared part per route (a slow day
        slows every leg) and a part per leg.
        """
        svc = self.predict_service(df)
        log_ratio = np.log(df["service_min"] / svc)
        self.pools["service"] = {b: log_ratio[df["brand"] == b].to_numpy() for b in df["brand"].unique()}

        travel_res = self._travel_target(df) - self.travel_model.predict(df[self.travel_features])
        route_effect = travel_res.groupby(df["route_id"]).transform("mean")
        self.pools["travel_route"] = travel_res.groupby(df["route_id"]).mean().to_numpy()
        self.pools["travel_leg"] = (travel_res - route_effect).to_numpy()

        f1 = self._first_legs(df)
        self.pools["delay"] = (self._delay_target(f1) - self.delay_model.predict(f1[self.delay_features])).to_numpy()
        return self

    # ---------- prediction ----------
    def predict_service(self, df: pd.DataFrame) -> np.ndarray:
        return np.clip(self.service_model.predict(df[self.service_features]), 1, None)

    def simulate(self, df: pd.DataFrame, n_sims: int = None) -> pd.DataFrame:
        """Replay every route in `df` and return per-stop service, P(late) and arrival bands."""
        n_sims = n_sims or self.n_sims
        rng = np.random.default_rng(self.seed)
        d = df.sort_values(["route_id", "seq"])
        routes, r_idx = np.unique(d["route_id"].to_numpy(), return_inverse=True)
        pos = d["seq"].to_numpy().astype(int)
        R, L = len(routes), pos.max() + 1

        def grid(values, fill=np.nan):
            g = np.full((R, L), fill, dtype=float)
            g[r_idx, pos] = values
            return g

        present = grid(np.ones(len(d)), 0).astype(bool)
        svc_pred = self.predict_service(d)
        travel_pred = d["planned_travel_min"].to_numpy() * np.exp(self.travel_model.predict(d[self.travel_features]))
        svc_g, trav_g = grid(svc_pred), grid(travel_pred)
        open_g = grid(d["window_open_time_min"].to_numpy())
        close_g = grid(d["window_close_time_min"].to_numpy())

        first = d[d["seq"] == 0]
        ridx = np.searchsorted(routes, first["route_id"].to_numpy())
        planned_start, delay_pred = np.full(R, np.nan), np.full(R, np.nan)
        planned_start[ridx] = first["planned_depart_time_min"].to_numpy()
        delay_pred[ridx] = self.delay_model.predict(first[self.delay_features])

        # Noise, sampled from the stored out-of-time residuals
        delay_noise = rng.choice(self.pools["delay"], size=(R, n_sims))
        route_eff = rng.choice(self.pools["travel_route"], size=(R, 1, n_sims))
        leg_noise = rng.choice(self.pools["travel_leg"], size=(R, L, n_sims))
        brands = grid(pd.Categorical(d["brand"]).codes)
        brand_names = list(pd.Categorical(d["brand"]).categories)
        svc_noise = np.zeros((R, L, n_sims))
        for code, name in enumerate(brand_names):
            mask = brands == code
            svc_noise[mask] = rng.choice(self.pools["service"][name], size=(mask.sum(), n_sims))

        travel = trav_g[..., None] * np.exp(route_eff + leg_noise)
        service = svc_g[..., None] * np.exp(svc_noise)

        delay = np.clip(delay_pred[:, None] + delay_noise, 0, None)  # vehicles never leave early
        t = planned_start[:, None] + delay
        arrival = np.full((R, L, n_sims), np.nan)
        for l in range(L):
            arr = np.round(t + travel[:, l])
            arrival[:, l] = arr
            begin = np.maximum(arr, open_g[:, l, None])
            t = np.where(present[:, l, None], begin + service[:, l], t)

        late = arrival > close_g[..., None]
        out = pd.DataFrame({
            "delivery_id": d["delivery_id"].to_numpy(),
            "pred_service_min": svc_pred,
            "sim_late_prob": late[r_idx, pos].mean(axis=1),
            "arrival_p50_min": np.median(arrival[r_idx, pos], axis=1),
            "arrival_p90_min": np.quantile(arrival[r_idx, pos], 0.9, axis=1),
            "planned_arrival_min": d["planned_arrival_min"].to_numpy(),
        })
        return out.set_index("delivery_id").reindex(df["delivery_id"]).reset_index()
