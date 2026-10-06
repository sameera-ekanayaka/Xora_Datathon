"""Task 1 features, built only from what a planner knows at the 4 PM cutoff.

Every function takes the stops table from notebook 03 (plus reference tables)
and returns one row per stop, indexed like the input. Nothing here reads an
actual time from the day being predicted. History features only look at days
that had fully finished before the cutoff.
"""

import numpy as np
import pandas as pd

# Plans for day D are drafted at 4 PM on D-1, when D-1's own routes may still
# be running. So the newest results a planner can trust are from D-2.
HISTORY_LAG_DAYS = 2

# How many past stops an outlet needs before its own average outweighs the
# wider group's. Small outlets lean on the group, busy ones on themselves.
SMOOTHING = 20

ACTUAL_COLS = [
    "actual_depart_time_min", "actual_travel_duration_min", "arrival_time_min",
    "leave_outlet_time_min", "wait_min", "service_min", "dwell_min", "late", "late_by_min",
]


def order_features(stops: pd.DataFrame, outlets: pd.DataFrame, vehicles: pd.DataFrame,
                   allowance: pd.DataFrame) -> pd.DataFrame:
    """What is being delivered, where, and on what vehicle."""
    veh = vehicles.set_index("vehicle_id")[["volume_cap_m3", "weight_cap_kg"]]
    mall = outlets.set_index("outlet_id")["mall_window"].notna().astype("int8")
    allow = allowance.set_index(["brand", "dock_type"])["service_allowance_min"]

    f = pd.DataFrame(index=stops.index)
    for col in ["brand", "depot", "district", "temp_requirement", "dock_type",
                "parking_constraint", "vehicle_type", "vehicle_temp", "outlet_id"]:
        f[col] = stops[col].astype("category")
    f["order_units"] = stops["order_units"]
    f["order_weight_kg"] = stops["order_weight_kg"]
    f["order_volume_m3"] = stops["order_volume_m3"]
    f["kg_per_unit"] = stops["order_weight_kg"] / stops["order_units"].clip(lower=1)
    f["is_chilled"] = (stops["temp_requirement"] == "chilled").astype("int8")
    f["is_mall"] = stops["outlet_id"].map(mall).astype("int8")
    f["was_deferred"] = (stops["dispatch_status"] == "deferred").astype("int8")
    f["vehicle_volume_cap_m3"] = stops["vehicle_id"].map(veh["volume_cap_m3"])
    f["vehicle_weight_cap_kg"] = stops["vehicle_id"].map(veh["weight_cap_kg"])
    f["allowance_min"] = pd.MultiIndex.from_frame(stops[["brand", "dock_type"]]).map(allow).to_numpy()
    return f


def route_features(stops: pd.DataFrame) -> pd.DataFrame:
    """Where the stop sits in the drafted route, and how tight its plan is."""
    s = stops.sort_values(["route_id", "seq"])
    g = s.groupby("route_id", sort=False)

    f = pd.DataFrame(index=s.index)
    f["seq"] = s["seq"]
    f["is_first_stop"] = (s["seq"] == 0).astype("int8")
    f["route_n_stops"] = g["seq"].transform("size")
    f["stops_after"] = f["route_n_stops"] - s["seq"] - 1
    f["same_outlet_as_previous"] = (s["from_point"] == s["outlet_id"]).astype("int8")

    f["route_volume_m3"] = g["order_volume_m3"].transform("sum")
    f["route_weight_kg"] = g["order_weight_kg"].transform("sum")
    f["volume_before_m3"] = g["order_volume_m3"].cumsum() - s["order_volume_m3"]
    f["route_distance_km"] = g["distance_km"].transform("sum")
    f["distance_so_far_km"] = g["distance_km"].cumsum()
    f["leg_distance_km"] = s["distance_km"]
    f["planned_travel_min"] = s["planned_travel_duration_min"]
    f["planned_travel_so_far_min"] = g["planned_travel_duration_min"].cumsum()

    start = g["planned_depart_time_min"].transform("first")
    arrive = s["planned_arrival_time_min_x"]
    f["route_start_min"] = start
    f["planned_arrival_min"] = arrive
    f["planned_hour"] = (arrive // 60).astype("int16")
    f["minutes_into_route"] = arrive - start

    f["window_length_min"] = s["window_close_time_min"] - s["window_open_time_min"]
    f["planned_slack_min"] = s["window_close_time_min"] - arrive
    f["planned_early_min"] = (s["window_open_time_min"] - arrive).clip(lower=0)
    # The tightest slack from here to the end of the route: a delay now
    # threatens every later stop too.
    f["min_slack_ahead_min"] = (
        f["planned_slack_min"].iloc[::-1].groupby(s["route_id"].iloc[::-1], sort=False).cummin().iloc[::-1]
    )
    return f.reindex(stops.index)


def calendar_features(stops: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Day of week, paydays, festivals and monsoon for the delivery date."""
    cal = calendar.set_index("date")
    fest_dates = cal.index[cal["festival"] != "none"].sort_values()

    d = stops["date"]
    f = pd.DataFrame(index=stops.index)
    f["dow"] = d.dt.dayofweek.astype("int8")
    f["month"] = d.dt.month.astype("int8")
    for col in ["is_payday", "is_holiday", "monsoon", "festival_ramp"]:
        f[col] = d.map(cal[col])
    f["is_festival_day"] = d.map(cal["festival"] != "none").astype("int8")

    # Days until the next festival, capped at 60 so far-off festivals look the same
    pos = np.searchsorted(fest_dates.values, d.values)
    nxt = pd.Series(fest_dates.append(pd.DatetimeIndex([pd.NaT]))[pos], index=stops.index)
    f["days_to_festival"] = (nxt - d).dt.days.fillna(60).clip(upper=60).astype("int16")
    f["trend_days"] = (d - pd.Timestamp("2024-01-01")).dt.days.astype("int32")
    return f


def condition_features(stops: pd.DataFrame, route_f: pd.DataFrame, road: pd.DataFrame,
                       traffic: pd.DataFrame) -> pd.DataFrame:
    """Road advisory for the day and the usual traffic at the planned hour."""
    road_idx = road.set_index(["district", "date"])["disruption_index"]
    speed_idx = traffic.set_index(["district", "hour", "monsoon"])["speed_index"]

    f = pd.DataFrame(index=stops.index)
    f["disruption_index"] = pd.MultiIndex.from_frame(stops[["district", "date"]]).map(road_idx).to_numpy()
    hour = route_f["planned_hour"].clip(upper=23)
    keys = pd.MultiIndex.from_arrays([stops["district"], hour, stops["monsoon"]])
    f["speed_index"] = keys.map(speed_idx).to_numpy()
    return f


def _asof_stats(rows: pd.DataFrame, events: pd.DataFrame, by: list, values: list) -> pd.DataFrame:
    """Running count and sums of `values` per `by` group, as known on each row's date.

    `events` carries one row per past stop with its date. Each day's results
    only become usable HISTORY_LAG_DAYS later.
    """
    daily = events.groupby(by + ["date"], observed=True)[values].agg(["sum", "count"])
    daily.columns = [f"{v}_{a}" for v, a in daily.columns]
    daily = daily.reset_index().sort_values("date")
    cum_cols = [c for c in daily.columns if c.endswith(("_sum", "_count"))]
    daily[cum_cols] = daily.groupby(by, observed=True)[cum_cols].cumsum()
    daily["usable_from"] = daily["date"] + pd.Timedelta(days=HISTORY_LAG_DAYS)

    left = rows[by + ["date"]].reset_index().sort_values("date")
    out = pd.merge_asof(
        left, daily.drop(columns="date"), left_on="date", right_on="usable_from",
        by=by, direction="backward",
    ).set_index("index").reindex(rows.index)
    return out[cum_cols].fillna(0)


def _smoothed(total, count, prior, k=SMOOTHING):
    return (total + k * prior) / (count + k)


def history_features(stops: pd.DataFrame) -> pd.DataFrame:
    """How each outlet, vehicle and district has behaved before, using only finished days."""
    done = stops[stops["service_min"].notna()].copy()
    done["late_f"] = done["late"].astype("float64")
    done["travel_ratio"] = done["actual_travel_duration_min"] / done["planned_travel_duration_min"].clip(lower=1)
    first = done[done["seq"] == 0].copy()
    first["depart_delay"] = first["actual_depart_time_min"] - first["planned_depart_time_min"]

    f = pd.DataFrame(index=stops.index)

    # Group-level priors, themselves built only from past days
    grp = _asof_stats(stops, done, ["brand", "dock_type"], ["service_min", "late_f"])
    grp_service = grp["service_min_sum"] / grp["service_min_count"].replace(0, np.nan)
    grp_late = grp["late_f_sum"] / grp["late_f_count"].replace(0, np.nan)
    f["group_hist_service_mean"] = grp_service

    out = _asof_stats(stops, done, ["outlet_id"], ["service_min", "late_f"])
    f["outlet_hist_stops"] = out["service_min_count"]
    f["outlet_hist_service_mean"] = _smoothed(out["service_min_sum"], out["service_min_count"], grp_service)
    f["outlet_hist_late_rate"] = _smoothed(out["late_f_sum"], out["late_f_count"], grp_late)

    dist = _asof_stats(stops, done, ["district", "monsoon"], ["travel_ratio"])
    f["district_hist_travel_ratio"] = dist["travel_ratio_sum"] / dist["travel_ratio_count"].replace(0, np.nan)

    depot = _asof_stats(stops, first, ["depot"], ["depart_delay"])
    depot_delay = depot["depart_delay_sum"] / depot["depart_delay_count"].replace(0, np.nan)
    veh = _asof_stats(stops, first, ["vehicle_id"], ["depart_delay"])
    f["vehicle_hist_depart_delay"] = _smoothed(veh["depart_delay_sum"], veh["depart_delay_count"], depot_delay)
    return f


def build_task1_features(stops, outlets, vehicles, allowance, calendar, road, traffic) -> pd.DataFrame:
    """All Task 1 features for every stop, train and test alike."""
    route_f = route_features(stops)
    parts = [
        order_features(stops, outlets, vehicles, allowance),
        route_f,
        calendar_features(stops, calendar),
        condition_features(stops, route_f, road, traffic),
        history_features(stops),
    ]
    feats = pd.concat(parts, axis=1)
    # A few combinations of the plan with history
    feats["load_share_volume"] = feats["route_volume_m3"] / feats["vehicle_volume_cap_m3"]
    feats["load_share_weight"] = feats["route_weight_kg"] / feats["vehicle_weight_cap_kg"]
    feats["expected_travel_min"] = feats["planned_travel_min"] * feats["district_hist_travel_ratio"]
    feats["slack_after_history_min"] = (
        feats["planned_slack_min"]
        - feats["planned_travel_so_far_min"] * (feats["district_hist_travel_ratio"] - 1)
        - feats["vehicle_hist_depart_delay"]
    )
    return feats
