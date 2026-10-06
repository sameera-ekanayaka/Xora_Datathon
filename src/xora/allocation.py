"""Task 2B: allocate the available fleet to one day's orders.

Every order is either served on a (vehicle, trip) or deferred. The plan has to
follow Waypoint's operating rules:
- one brand and one district per trip, whole orders only
- chilled goods only on reefers, van_only outlets only by van
- volume and weight within the vehicle's caps
- at most two trips per vehicle, Fresh trips within the 270 minute pre-dawn
  budget and Style and Tech trips within the 480 minute day

Within those rules the plan is chosen by a strict order of priorities. Each
priority is solved to its best value and then locked in before the next one is
looked at, so a lower priority can never buy itself a better score by giving up
something higher up:
1. serve the orders that were already deferred yesterday
2. serve chilled volume, which spoils if it waits a day
3. serve the rest of the Fresh volume, which has to be on shelves before 8 AM
4. serve as much volume overall as possible
5. run as few second pre-dawn trips as possible, since a vehicle that has to
   drive back and reload rarely makes the 8 AM opening (see `timeline`)
6. drive as few kilometres as possible

Chilled volume has one refinement. The best chilled plans are nearly tied, and
a plan that is 0.3 m3 better can leave a whole district without chilled goods.
So the chilled step may give up at most 1% of the best chilled volume, and
uses that room to get chilled orders to as many outlets as possible. Among
plans that reach that many outlets, it then serves as much chilled volume as
it can.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pulp

TRIPS = (1, 2)
FRESH_BUDGET_MIN = 270
DAY_BUDGET_MIN = 480

# (name, direction, plain-language label, share of the best value we may give up)
PRIORITIES = [
    ("repeat_deferrals_served", "max", "orders deferred yesterday that are served today", 0.0),
    ("chilled_m3", "max", "chilled volume served (m3)", 0.01),
    ("chilled_orders", "max", "outlets that get their chilled order", 0.0),
    ("chilled_m3_for_those_outlets", "max", "chilled volume served, reaching those outlets (m3)", 0.0),
    ("fresh_ambient_m3", "max", "Fresh ambient volume served (m3)", 0.0),
    ("total_m3", "max", "total volume served (m3)", 0.0),
    ("second_fresh_trips", "min", "vehicles running a second pre-dawn Fresh trip", 0.0),
    ("trip_km", "min", "kilometres driven, depot and back", 0.0),
]


@dataclass
class Problem:
    orders: pd.DataFrame
    vehicles: pd.DataFrame
    travel: pd.DataFrame
    allowance: dict
    groups: list = field(init=False)

    def __post_init__(self):
        o = self.orders.copy()
        o["group"] = list(zip(o["brand"], o["district"]))
        o["allowance_min"] = [self.allowance[(b, d)] for b, d in zip(o["brand"], o["dock_type"])]
        self.orders = o.set_index("order_ref", drop=False)
        self.vehicles = self.vehicles.set_index("vehicle_id", drop=False)
        self.travel = self.travel.set_index("district")
        self.groups = sorted(o["group"].unique())

    def subset(self, order_mask, vehicle_mask) -> "Problem":
        """A smaller problem over some of the orders and some of the vehicles."""
        o = self.orders.reset_index(drop=True)
        v = self.vehicles.reset_index(drop=True)
        return Problem(o[order_mask(o)].drop(columns=["group", "allowance_min"]),
                       v[vehicle_mask(v)], self.travel.reset_index(), self.allowance)

    def can_carry(self, order, veh) -> bool:
        """Whether a vehicle may ever carry this order, before capacity is shared."""
        if veh["depot"] != order["depot"]:
            return False
        if order["temp_requirement"] == "chilled" and veh["temp"] != "reefer":
            return False
        if order["parking_constraint"] == "van_only" and veh["type"] != "van":
            return False
        return (order["order_volume_m3"] <= veh["volume_cap_m3"]
                and order["order_weight_kg"] <= veh["weight_cap_kg"])


def load_problem(scenarios, fleet, vehicles, travel, allowance, scenario="S1", extra_vehicles=()):
    """Orders and available vehicles for one scenario.

    `extra_vehicles` adds vehicles that are in the workshop, for what-if runs.
    """
    status = fleet[fleet["scenario"] == scenario].set_index("vehicle_id")["status"]
    ids = list(status[status == "available"].index) + list(extra_vehicles)
    allow = {(r.brand, r.dock_type): r.service_allowance_min for r in allowance.itertuples()}
    return Problem(
        orders=scenarios[scenarios["scenario"] == scenario].reset_index(drop=True),
        vehicles=vehicles[vehicles["vehicle_id"].isin(ids)].reset_index(drop=True),
        travel=travel,
        allowance=allow,
    )


class AllocationModel:
    """The assignment model, built once and re-solved priority by priority."""

    def __init__(self, prob: Problem):
        self.prob = prob
        o, v, tr = prob.orders, prob.vehicles, prob.travel
        m = pulp.LpProblem("allocation", pulp.LpMaximize)

        # x: order on (vehicle, trip). y: the trip runs for one (brand, district).
        self.x = {(oid, vid, t): pulp.LpVariable(f"x_{oid}_{vid}_{t}", cat="Binary")
                  for oid, order in o.iterrows() for vid, veh in v.iterrows()
                  if prob.can_carry(order, veh) for t in TRIPS}
        self.y = {(vid, t, g): pulp.LpVariable(f"y_{vid}_{t}_{g[0]}_{g[1]}", cat="Binary")
                  for vid in v.index for t in TRIPS for g in prob.groups}
        x, y = self.x, self.y

        by_order, by_trip = {}, {}
        for (oid, vid, t), var in x.items():
            by_order.setdefault(oid, []).append(var)
            by_trip.setdefault((vid, t), []).append((oid, var))

        self.served = {oid: pulp.lpSum(by_order.get(oid, [])) for oid in o.index}
        for oid in o.index:
            m += self.served[oid] <= 1, f"once_{oid}"

        def trip_volume(vid, t):
            return pulp.lpSum(var * o.at[oid, "order_volume_m3"] for oid, var in by_trip.get((vid, t), []))

        trip_minutes = {}
        for vid, veh in v.iterrows():
            for t in TRIPS:
                stops = by_trip.get((vid, t), [])
                m += pulp.lpSum(y[vid, t, g] for g in prob.groups) <= 1, f"one_group_{vid}_{t}"
                for oid, var in stops:
                    m += var <= y[vid, t, o.at[oid, "group"]], f"match_{oid}_{vid}_{t}"
                m += pulp.lpSum(var * o.at[oid, "order_volume_m3"] for oid, var in stops) <= veh["volume_cap_m3"], f"vol_{vid}_{t}"
                m += pulp.lpSum(var * o.at[oid, "order_weight_kg"] for oid, var in stops) <= veh["weight_cap_kg"], f"kg_{vid}_{t}"
                # A trip only runs if it carries something
                for g in prob.groups:
                    m += y[vid, t, g] <= pulp.lpSum(var for oid, var in stops if o.at[oid, "group"] == g), f"used_{vid}_{t}_{g[0]}_{g[1]}"
                # Planned minutes: outbound once, then a hop and a handling time per extra stop
                for brand_is_fresh in (True, False):
                    gs = [g for g in prob.groups if (g[0] == "Fresh") == brand_is_fresh]
                    trip_minutes[vid, t, brand_is_fresh] = (
                        pulp.lpSum(y[vid, t, g] * (tr.at[g[1], "depot_to_district_freeflow_min"]
                                                   - tr.at[g[1], "inter_stop_freeflow_min"]) for g in gs)
                        + pulp.lpSum(var * (o.at[oid, "allowance_min"] + tr.at[o.at[oid, "district"], "inter_stop_freeflow_min"])
                                     for oid, var in stops if (o.at[oid, "brand"] == "Fresh") == brand_is_fresh)
                    )
            # Trips 1 and 2 are interchangeable here, so let trip 1 always be the fuller one.
            # The run order is settled later by `timeline`.
            m += trip_volume(vid, 2) <= trip_volume(vid, 1), f"order_{vid}"
            m += pulp.lpSum(trip_minutes[vid, t, True] for t in TRIPS) <= FRESH_BUDGET_MIN, f"fresh_budget_{vid}"
            m += pulp.lpSum(trip_minutes[vid, t, False] for t in TRIPS) <= DAY_BUDGET_MIN, f"day_budget_{vid}"

        # Identical vehicles are interchangeable too: fill them in id order.
        # Without this the solver wastes most of its time on mirror-image plans.
        spec = ["type", "temp", "volume_cap_m3", "weight_cap_kg", "depot"]
        for _, same in v.groupby(spec):
            ids = list(same.index)
            for a, b in zip(ids, ids[1:]):
                m += trip_volume(b, 1) <= trip_volume(a, 1), f"same_{a}_{b}"

        # Fresh trips beyond the first, per vehicle
        extra_fresh = []
        fresh_groups = [g for g in prob.groups if g[0] == "Fresh"]
        for vid in v.index:
            z = pulp.LpVariable(f"extra_fresh_{vid}", lowBound=0, cat="Integer")
            m += z >= pulp.lpSum(y[vid, t, g] for t in TRIPS for g in fresh_groups) - 1, f"extra_fresh_{vid}"
            extra_fresh.append(z)

        def served_sum(mask, weight):
            return pulp.lpSum(self.served[oid] * w for oid, w in weight[mask].items())

        vol = o["order_volume_m3"]
        self.objectives = {
            "repeat_deferrals_served": served_sum(o["deferred_yesterday"] == 1, pd.Series(1.0, index=o.index)),
            "chilled_m3": served_sum(o["temp_requirement"] == "chilled", vol),
            "chilled_orders": served_sum(o["temp_requirement"] == "chilled", pd.Series(1.0, index=o.index)),
            # Then win back as much chilled volume as possible while reaching those outlets
            "chilled_m3_for_those_outlets": served_sum(o["temp_requirement"] == "chilled", vol),
            "fresh_ambient_m3": served_sum((o["brand"] == "Fresh") & (o["temp_requirement"] == "ambient"), vol),
            "total_m3": served_sum(pd.Series(True, index=o.index), vol),
            "second_fresh_trips": pulp.lpSum(extra_fresh),
            "trip_km": (pulp.lpSum(y[vid, t, g] * (2 * tr.at[g[1], "depot_to_district_km"] - tr.at[g[1], "inter_stop_km"])
                                   for (vid, t, g) in y)
                        + pulp.lpSum(var * tr.at[o.at[oid, "district"], "inter_stop_km"] for (oid, _, _), var in x.items())),
        }
        self.model = m

    def solve(self, priorities=PRIORITIES, force=None, pin=(), time_limit=120, tol=1e-4):
        """Solve each priority in turn and lock it in.

        `force` maps order_ref to 1 (must be served) or 0 (must be deferred),
        for testing what a different decision would cost. `pin` lists
        (order_ref, vehicle_id, trip_id) assignments that are already decided.
        """
        m = self.model.copy()
        for oid, val in (force or {}).items():
            m += self.served[oid] == val, f"force_{oid}"
        for key in pin:
            m += self.x[key] == 1, f"pin_{'_'.join(map(str, key))}"
        achieved, self.proven = {}, {}  # achieved: best value of each step when it was solved
        for name, sense, _, slack in priorities:
            expr = self.objectives[name]
            m.sense = pulp.LpMaximize if sense == "max" else pulp.LpMinimize
            m.setObjective(expr)
            # Each step starts from the previous plan, which already meets every lock
            status = m.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit, gapRel=0, warmStart=bool(achieved)))
            if pulp.LpStatus[status] != "Optimal":
                return None, {"status": pulp.LpStatus[status]}
            best = pulp.value(expr) or 0.0
            achieved[name] = round(best, 4)
            # CBC stops at the time limit with its best plan so far; note when that happened
            self.proven[name] = m.sol_status == pulp.LpSolutionOptimal
            m += (expr >= best * (1 - slack) - tol) if sense == "max" else (expr <= best * (1 + slack) + tol), f"lock_{name}"
        # Report what the final plan delivers, which can sit inside a step's allowed slack
        final = {name: round(pulp.value(self.objectives[name]) or 0.0, 4) for name, *_ in priorities}
        return self._plan(), final

    def _plan(self) -> pd.DataFrame:
        o = self.prob.orders
        rows = {oid: ("deferred", None, None) for oid in o.index}
        for (oid, vid, t), var in self.x.items():
            if var.value() is not None and var.value() > 0.5:
                rows[oid] = ("served", vid, t)
        plan = pd.DataFrame([(oid, *r) for oid, r in rows.items()],
                            columns=["order_ref", "decision", "vehicle_id", "trip_id"])
        plan["trip_id"] = plan["trip_id"].astype("Int64")
        return o.drop(columns=["group"]).reset_index(drop=True).merge(plan, on="order_ref")


def trip_table(plan: pd.DataFrame, prob: Problem) -> pd.DataFrame:
    """One row per trip with its load, planned minutes and kilometres."""
    tr, veh = prob.travel, prob.vehicles
    s = plan[plan["decision"] == "served"]
    rows = []
    for (vid, t), g in s.groupby(["vehicle_id", "trip_id"]):
        d, n = g["district"].iloc[0], len(g)
        rows.append({
            "vehicle_id": vid, "trip_id": t, "type": veh.at[vid, "type"], "temp": veh.at[vid, "temp"],
            "brand": g["brand"].iloc[0], "district": d, "orders": n,
            "chilled_orders": int((g["temp_requirement"] == "chilled").sum()),
            "volume_m3": g["order_volume_m3"].sum(), "volume_cap_m3": veh.at[vid, "volume_cap_m3"],
            "weight_kg": g["order_weight_kg"].sum(), "weight_cap_kg": veh.at[vid, "weight_cap_kg"],
            "planned_min": tr.at[d, "depot_to_district_freeflow_min"] + (n - 1) * tr.at[d, "inter_stop_freeflow_min"]
                           + g["allowance_min"].sum(),
            "km": 2 * tr.at[d, "depot_to_district_km"] + (n - 1) * tr.at[d, "inter_stop_km"],
        })
    out = pd.DataFrame(rows)
    out["volume_fill"] = out["volume_m3"] / out["volume_cap_m3"]
    out["weight_fill"] = out["weight_kg"] / out["weight_cap_kg"]
    return out


def to_submission(plan: pd.DataFrame, scenario="S1") -> pd.DataFrame:
    out = plan[["order_ref", "outlet_id", "decision", "vehicle_id", "trip_id"]].copy()
    out.insert(0, "scenario", scenario)
    return out.sort_values("order_ref").reset_index(drop=True)


REEFER_PRIORITIES = [p for p in PRIORITIES if p[0] in ("repeat_deferrals_served", "chilled_m3", "chilled_orders",
                                                      "chilled_m3_for_those_outlets", "trip_km")]


def plan_day(prob: Problem, force=None, time_limit=120):
    """Plan the day in two stages and return the plan and what each stage achieved.

    Chilled orders can only ride on the few reefers, and that is where the day
    is decided. Stage 1 packs the chilled orders onto the reefers by the same
    priorities. Stage 2 keeps those reefer loads and plans everything else on
    the whole fleet, which may still top up a reefer trip with ambient orders
    for the same outlets' district.

    Splitting the solve this way is exact for the first four priorities as long
    as stage 2 serves every ambient order that fits on any vehicle, because
    ambient orders never compete with chilled ones for a reefer then. The
    notebook checks that condition.
    """
    force = force or {}
    chilled = lambda o: o["temp_requirement"] == "chilled"
    reefer = prob.subset(chilled, lambda v: v["temp"] == "reefer")
    m1 = AllocationModel(reefer)
    stage1, got1 = m1.solve(
        REEFER_PRIORITIES, force={k: f for k, f in force.items() if k in reefer.orders.index},
        time_limit=time_limit)
    if stage1 is None:
        return None, {"stage1": got1}

    served = stage1[stage1["decision"] == "served"]
    pin = list(zip(served["order_ref"], served["vehicle_id"], served["trip_id"].astype(int)))
    keep_out = {oid: 0 for oid in stage1.loc[stage1["decision"] == "deferred", "order_ref"]}
    m2 = AllocationModel(prob)
    plan, got2 = m2.solve(PRIORITIES, force={**force, **keep_out}, pin=pin, time_limit=time_limit)
    return plan, {"stage1": got1, "stage2": got2, "proven": {"stage1": m1.proven, "stage2": m2.proven}}


FRESH_START_MIN = 3 * 60 + 30   # 03:30, start of the pre-dawn window
DAY_START_MIN = 7 * 60 + 30     # earliest Style and Tech departures in the route history


def _clock(minutes):
    return pd.to_datetime(pd.Series(minutes).round(), unit="m").dt.strftime("%H:%M").to_numpy()


def _hhmm(text):
    h, m = str(text).split(":")
    return int(h) * 60 + int(m)


def timeline(plan: pd.DataFrame, prob: Problem, travel_ratio=None, service_ratio=None, depart_delay=0.0):
    """Clock times for every served stop, with the drive back between trips.

    The planning standard checks minutes per window but not the clock, so this
    replays each vehicle's day:
    - Fresh trips start from 03:30 and Style and Tech trips from 07:30
    - a vehicle leaves no earlier than it needs to reach its first outlet as it opens
    - within a trip, the stop order with the fewest late arrivals is used
    - a second trip in the same window loads after the first one drives back
    - when a vehicle has two trips in one window, both orders are tried and the
      one with fewer late stops is kept, and trips are renumbered in run order

    `travel_ratio` maps (brand, district) to actual over planned drive time and
    `service_ratio` maps (brand, dock_type) to actual over allowed handling
    time, so the same replay can be run on the standard or on a typical day.
    """
    tr = prob.travel
    travel_ratio = travel_ratio or {}
    service_ratio = service_ratio or {}
    s = plan[plan["decision"] == "served"].copy()
    s["open_min"] = s["window_open_time"].map(_hhmm)
    s["close_min"] = s["window_close_time"].map(_hhmm)

    def drive(g, ready):
        """Replay one trip with its stops in the given order."""
        brand, dist = g["brand"].iloc[0], g["district"].iloc[0]
        k = travel_ratio.get((brand, dist), 1.0)
        out_min = tr.at[dist, "depot_to_district_freeflow_min"] * k
        hop = tr.at[dist, "inter_stop_freeflow_min"] * k
        t = max(ready, g["open_min"].iloc[0] - out_min) + depart_delay
        t_depart = t
        rows = []
        for i, (_, r) in enumerate(g.iterrows()):
            t += out_min if i == 0 else hop
            arrive = t
            t = max(t, r["open_min"]) + r["allowance_min"] * service_ratio.get((brand, r["dock_type"]), 1.0)
            rows.append((r["order_ref"], i + 1, t_depart, arrive, arrive - r["close_min"]))
        return rows, t + out_min  # back at the depot

    def score(rows):
        late = [x[-1] for x in rows if x[-1] > 0]
        return len(late), sum(late)

    def run_trip(g, ready):
        """Pick a stop order: the best of a few sensible sorts, then improve it by swapping pairs."""
        starts = [g.sort_values(c) for c in (["close_min", "open_min"], ["open_min", "close_min"])]
        best = min(starts, key=lambda o: score(drive(o, ready)[0]))
        improved = True
        while improved:
            improved = False
            for i in range(len(best)):
                for j in range(i + 1, len(best)):
                    idx = list(range(len(best)))
                    idx[i], idx[j] = idx[j], idx[i]
                    cand = best.iloc[idx]
                    if score(drive(cand, ready)[0]) < score(drive(best, ready)[0]):
                        best, improved = cand, True
        return drive(best, ready)

    out = []
    for vid, v in s.groupby("vehicle_id"):
        trips = dict(tuple(v.groupby("trip_id")))
        fresh = [t for t, g in trips.items() if g["brand"].iloc[0] == "Fresh"]
        day = [t for t in trips if t not in fresh]
        ready, best_runs = {}, []
        for window, start in ((fresh, FRESH_START_MIN), (day, DAY_START_MIN)):
            options = [window] if len(window) < 2 else [window, window[::-1]]
            scored = []
            for order in options:
                clock = max(start, ready.get("back", 0))
                rows = []
                for t in order:
                    r, clock = run_trip(trips[t], clock)
                    rows += [(t, *x) for x in r]
                late = [x[-1] for x in rows if x[-1] > 0]
                scored.append((len(late), sum(late), rows, clock))
            if scored:
                n_late, total_late, rows, clock = min(scored, key=lambda z: (z[0], z[1]))
                ready["back"] = clock
                best_runs += rows
        run_order = list(dict.fromkeys(r[0] for r in best_runs))
        for t, oid, stop_no, dep, arr, late_by in best_runs:
            out.append((vid, run_order.index(t) + 1, t, oid, stop_no, dep, arr, late_by))

    tl = pd.DataFrame(out, columns=["vehicle_id", "run", "trip_id", "order_ref", "stop_no",
                                    "depart_min", "arrive_min", "late_by_min"])
    tl = tl.merge(s[["order_ref", "outlet_id", "brand", "district", "temp_requirement",
                     "window_open_time", "window_close_time"]], on="order_ref")
    tl["depart"], tl["arrive"] = _clock(tl["depart_min"]), _clock(tl["arrive_min"])
    tl["late"] = tl["late_by_min"] > 0
    return tl.sort_values(["vehicle_id", "run", "stop_no"]).reset_index(drop=True)


def renumber_trips(plan: pd.DataFrame, tl: pd.DataFrame) -> pd.DataFrame:
    """Use the run order from `timeline` as the trip number, so trip 1 leaves first."""
    run = tl.drop_duplicates(["vehicle_id", "trip_id"]).set_index(["vehicle_id", "trip_id"])["run"]
    out = plan.copy()
    served = out["decision"] == "served"
    keys = pd.MultiIndex.from_frame(out.loc[served, ["vehicle_id", "trip_id"]].astype({"trip_id": int}))
    out.loc[served, "trip_id"] = run.reindex(keys).to_numpy()
    return out
