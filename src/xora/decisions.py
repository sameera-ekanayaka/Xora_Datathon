"""The decision layer: model outputs turned into plain instructions.

Dispatchers, loaders, drivers and store managers do not read probabilities.
Everything here follows the same rules:
- clock times, not minutes since midnight
- ranges, not single numbers
- a traffic light that always comes with an action
- one plain reason line, taken from the features that pushed the risk up most
"""

import numpy as np
import pandas as pd

# The late-risk blend is calibrated (notebook 05), so a stop shown red really
# is expected to run late at least half the time.
RED, AMBER = 0.50, 0.25

ACTIONS = {
    "red": "call the store before leaving; move the stop earlier or split the route",
    "amber": "watch it; the driver calls ahead if running behind",
    "green": "no action",
}


def clock(minutes) -> str:
    """Minutes since midnight as HH:MM."""
    m = int(round(float(minutes)))
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def light(p: float) -> str:
    return "red" if p >= RED else "amber" if p >= AMBER else "green"


def arrival_range(p50, p90) -> str:
    """Expected arrival as a range, rounded to five minutes so it does not look more precise than it is."""
    lo, hi = 5 * round(p50 / 5), 5 * round(p90 / 5)
    return clock(lo) if hi <= lo else f"{clock(lo)} to {clock(hi)}"


# One plain phrase per driver. Each takes the stop's row and returns text.
PHRASES = {
    "slack_after_history_min": lambda r: (f"only {r.slack_after_history_min:.0f} min to spare once usual traffic is counted"
                                          if r.slack_after_history_min > 0 else
                                          f"about {-r.slack_after_history_min:.0f} min past the cut-off once usual traffic is counted"),
    "planned_slack_min": lambda r: (f"the plan leaves {r.planned_slack_min:.0f} min before the cut-off"
                                    if r.planned_slack_min > 0 else "planned to arrive after the cut-off"),
    "min_slack_ahead_min": lambda r: "a tight stop later on the same route",
    "seq": lambda r: f"stop {int(r.seq) + 1} of {int(r.route_n_stops)}, delays build up",
    "minutes_into_route": lambda r: f"{r.minutes_into_route:.0f} min into the route",
    "stops_after": lambda r: f"stop {int(r.seq) + 1} of {int(r.route_n_stops)}",
    "disruption_index": lambda r: f"road advisory for {r.district} ({r.disruption_index:.0f}, 100 = clear)",
    "speed_index": lambda r: f"slow traffic in {r.district} at this hour",
    "district_hist_travel_ratio": lambda r: f"roads in {r.district} usually take {r.district_hist_travel_ratio:.1f}x the plan",
    "expected_travel_min": lambda r: f"long drive to this stop ({r.expected_travel_min:.0f} min expected)",
    "monsoon": lambda r: "monsoon roads",
    "outlet_hist_late_rate": lambda r: f"this outlet's deliveries run late {r.outlet_hist_late_rate:.0%} of the time",
    "outlet_id": lambda r: f"{r.outlet_id} is often slow to receive",
    "outlet_hist_service_mean": lambda r: f"{r.outlet_id} usually takes {r.outlet_hist_service_mean:.0f} min to unload",
    "vehicle_hist_depart_delay": lambda r: f"this vehicle usually leaves {r.vehicle_hist_depart_delay:.0f} min late",
    "route_start_min": lambda r: f"route starts at {clock(r.route_start_min)}",
    "planned_arrival_min": lambda r: f"planned arrival {clock(r.planned_arrival_min)}",
    "planned_hour": lambda r: f"planned arrival {clock(r.planned_arrival_min)}",
    "window_length_min": lambda r: f"short delivery window ({r.window_length_min:.0f} min)",
    "festival_ramp": lambda r: "festival rush",
    "days_to_festival": lambda r: f"{int(r.days_to_festival)} days before a festival",
    "order_volume_m3": lambda r: f"large order ({r.order_volume_m3:.1f} m3)",
    "route_volume_m3": lambda r: f"heavily loaded route ({r.route_volume_m3:.0f} m3)",
    "load_share_volume": lambda r: f"vehicle {r.load_share_volume:.0%} full",
    "dock_type": lambda r: f"{str(r.dock_type).replace('_', ' ')} unloading",
}


def reason_line(row: pd.Series, contrib: pd.Series, n: int = 2) -> str:
    """The top drivers that pushed this stop's risk up, in words.

    `contrib` holds the classifier's per-feature contributions (SHAP values)
    for the stop. Drivers without a phrase are skipped, so the line stays readable.
    """
    words = []
    for feat in contrib[contrib > 0].sort_values(ascending=False).index:
        if feat in PHRASES:
            text = PHRASES[feat](row)
            if text not in words:
                words.append(text)
        if len(words) == n:
            break
    return "; ".join(words) if words else "no single strong driver"


def route_fix(stops: pd.DataFrame) -> str:
    """One suggested change for a route, from where its red stops sit."""
    red = stops.loc[stops.light == "red", "seq"]
    if red.empty:
        return "amber stops only: driver calls ahead if behind" if (stops.light == "amber").any() else "no change"
    if red.min() == 0:
        return "leave earlier: the route is at risk from its first stop"
    return f"split the route after stop {int(red.min())}, or move the red stops to the front"


def store_message(row) -> str:
    """The evening-before message to a store manager for one delivery."""
    when = arrival_range(row.arrival_p50_min, row.arrival_p90_min)
    closes = clock(row.window_close_time_min)
    brand = row.brand
    if row.light == "red":
        return (f"Your {brand} delivery is planned for {when}. It may arrive after your {closes} cut-off, "
                f"so the driver will call you on the way. Please keep the receiving bay free.")
    if row.light == "amber":
        return f"Your {brand} delivery should arrive {when}, before your {closes} cut-off on most days."
    return f"Your {brand} delivery arrives {when}, usually on time."


def deferral_message(row) -> str:
    """Message to a store whose order moves to tomorrow."""
    goods = "chilled order" if row.temp_requirement == "chilled" else f"{row.brand} order"
    if row.reason == "TOO_BIG_FOR_ANY_VEHICLE":
        why = (f"at {row.order_volume_m3:.1f} m3 it is bigger than any single truck can carry. "
               f"Could you split it into two orders? We will deliver both as a priority")
    else:
        why = "our refrigerated trucks are short today with several in the workshop"
    return (f"Your {goods} ({row.order_ref}) moves to tomorrow because {why}. "
            f"You are first in line tomorrow, and the rest of today's delivery comes as planned.")


def loading_sheet(plan: pd.DataFrame, tl: pd.DataFrame, trips: pd.DataFrame) -> pd.DataFrame:
    """Load order for every trip: the last stop goes in first, so the first stop is at the doors."""
    t = tl[["order_ref", "vehicle_id", "trip_id", "stop_no"]].merge(
        plan[["order_ref", "order_volume_m3", "order_weight_kg"]], on="order_ref")
    t = t.sort_values(["vehicle_id", "trip_id", "stop_no"], ascending=[True, True, False])
    t["load_order"] = t.groupby(["vehicle_id", "trip_id"]).cumcount() + 1
    t = t.merge(tl[["order_ref", "outlet_id", "temp_requirement"]], on="order_ref")
    t["section"] = np.where(t.temp_requirement == "chilled", "chilled", "ambient")
    fill = trips.set_index(["vehicle_id", "trip_id"])
    keys = list(zip(t.vehicle_id, t.trip_id))
    t["trip_fill"] = [f"{fill.at[k, 'volume_m3']:.1f} of {fill.at[k, 'volume_cap_m3']:.1f} m3, "
                      f"{fill.at[k, 'weight_kg']:.0f} of {fill.at[k, 'weight_cap_kg']:.0f} kg" for k in keys]
    t["check"] = ["count every case before closing the doors" if max(fill.at[k, "volume_fill"], fill.at[k, "weight_fill"]) >= 0.9
                  else "" for k in keys]
    return t[["vehicle_id", "trip_id", "load_order", "stop_no", "order_ref", "outlet_id", "section",
              "order_volume_m3", "order_weight_kg", "trip_fill", "check"]]


def reefer_outlook(forecast: pd.DataFrame, calendar: pd.DataFrame, daily_history: pd.DataFrame) -> pd.DataFrame:
    """Chilled volume per operating day for each forecast week, against what each depot has handled before.

    `daily_history` has one row per depot and day with the chilled volume
    delivered and the reefer trips run. A forecast day is compared with the
    depot's own busy days: above its 95th percentile it has rarely, if ever,
    coped without extra reefers.
    """
    ch = forecast[forecast.measure == "chilled"]
    days = calendar.groupby(["iso_year", "iso_week"]).is_operating.sum().rename("operating_days")
    out = ch.merge(days.reset_index(), on=["iso_year", "iso_week"])
    hist = daily_history.groupby("depot")
    busy90, busy95 = hist.chilled_m3.quantile(0.90), hist.chilled_m3.quantile(0.95)
    m3_per_trip = hist.chilled_m3.sum() / hist.reefer_trips.sum()
    for q in ["p50", "p90"]:
        out[f"m3_per_day_{q}"] = out[q] / out.operating_days.clip(lower=1)
        out[f"trips_per_day_{q}"] = out[f"m3_per_day_{q}"] / out.depot.map(m3_per_trip)
    out["busy_day_p90"], out["busy_day_p95"] = out.depot.map(busy90), out.depot.map(busy95)
    out["status"] = np.select([out.m3_per_day_p90 > out.busy_day_p95, out.m3_per_day_p90 > out.busy_day_p90],
                              ["red", "amber"], "green")
    out["advice"] = out.status.map({
        "red": "busier than 95% of days this depot has run: no reefer maintenance, line up second trips or a hired reefer",
        "amber": "busier than 9 days in 10: book reefer maintenance in another week",
        "green": "a normal load: a good week for reefer maintenance",
    })
    return out[["depot", "iso_year", "iso_week", "operating_days", "m3_per_day_p50", "m3_per_day_p90",
                "trips_per_day_p50", "trips_per_day_p90", "busy_day_p90", "busy_day_p95", "status", "advice"]]
