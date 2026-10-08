"""Build the small data bundle the Streamlit app reads.

Run after the notebooks, from the repo root:

    python app/build_app_data.py                 # everything except the workshop ranking
    python app/build_app_data.py --repairs       # also re-solve the workshop ranking (about 25 minutes)

The bundle only holds derived outputs (predictions, plans, forecasts and the
features the saved models need for the test period), never the raw files.
"""

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xora import allocation as al  # noqa: E402
from xora import decisions as dl  # noqa: E402
from xora import features as fe  # noqa: E402
from xora.io import load_processed, load_raw  # noqa: E402

OUT = ROOT / "app" / "data"
MODELS = ROOT / "models"


def task1_bundle():
    """Test-period stops with the model inputs, predictions, lights and reasons."""
    stops = load_processed("stops")
    tables = dict(outlets=load_processed("outlets"), vehicles=load_processed("vehicles"),
                  allowance=load_processed("service_allowance"), calendar=load_processed("calendar"),
                  road=load_processed("road_conditions"), traffic=load_processed("traffic_speed"))
    full = fe.model_frame(stops, fe.build_task1_features(stops, **tables))
    test = full[full.split == "test"].copy()

    simulator = joblib.load(MODELS / "route_simulator.pkl")
    classifier = joblib.load(MODELS / "late_classifier.pkl")
    task1 = pd.read_csv(ROOT / "submissions" / "submission_task1.csv")

    sim = simulator.simulate(test)[["delivery_id", "sim_late_prob", "arrival_p50_min", "arrival_p90_min"]]
    test = test.merge(task1, on="delivery_id").merge(sim, on="delivery_id")
    feats = classifier.feature_name_
    contrib = pd.DataFrame(classifier.booster_.predict(test[feats], pred_contrib=True)[:, :-1], columns=feats, index=test.index)

    test["light"] = test.pred_late_prob.map(dl.light)
    test["reason"] = [dl.reason_line(test.loc[i], contrib.loc[i]) if test.at[i, "light"] != "green" else ""
                      for i in test.index]
    # Labels of the test period are not part of the inputs, so they stay out of the bundle
    test = test.drop(columns=[c for c in ["actual_depart_time_min", "actual_travel_duration_min", "service_min", "late"]
                              if c in test.columns])
    test["date"] = pd.to_datetime(test["date"])
    test.to_parquet(OUT / "task1_test.parquet", index=False)
    return test


def task2a_bundle():
    load_processed("task2a_forecast").to_parquet(OUT / "task2a_forecast.parquet", index=False)
    weekly = load_processed("weekly_demand")
    weekly[["depot", "brand", "iso_year", "iso_week", "total_volume_m3_adj", "chilled_volume_m3_adj", "source"]].rename(
        columns={"total_volume_m3_adj": "total", "chilled_volume_m3_adj": "chilled"}).to_parquet(OUT / "weekly_history.parquet", index=False)
    cal = load_processed("calendar")
    fest = (cal[cal.festival != "none"].groupby(["iso_year", "iso_week"]).festival.first().reset_index())
    fest.to_parquet(OUT / "festival_weeks.parquet", index=False)
    pd.read_csv(ROOT / "reports" / "decision_layer" / "weekly_reefer_outlook.csv").to_parquet(OUT / "reefer_outlook.parquet", index=False)


def task2b_bundle(repairs: bool):
    plan, timeline = load_processed("task2b_plan"), load_processed("task2b_timeline")
    raw = [load_raw(f) for f in ["task2b_peak_day_scenarios.csv", "task2b_peak_day_fleet.csv", "vehicles.csv",
                                 "district_travel.csv", "service_allowance.csv"]]
    prob = al.load_problem(*raw)
    trips = al.trip_table(plan, prob)
    plan.to_parquet(OUT / "task2b_plan.parquet", index=False)
    timeline.to_parquet(OUT / "task2b_timeline.parquet", index=False)
    trips.to_parquet(OUT / "task2b_trips.parquet", index=False)
    for name in ["peak_day_deferral_list", "peak_day_store_notices", "peak_day_loading_sheets", "peak_day_late_warnings"]:
        pd.read_csv(ROOT / "reports" / "decision_layer" / f"{name}.csv").to_parquet(OUT / f"{name}.parquet", index=False)

    if repairs:
        # Same re-solve as the notebook: add one workshop reefer back and maximise chilled goods
        scenarios, fleet, vehicles = raw[0], raw[1], raw[2]
        workshop = fleet[(fleet.scenario == "S1") & (fleet.status != "available")].merge(vehicles, on="vehicle_id")
        base = plan[(plan.decision == "served") & (plan.temp_requirement == "chilled")]
        rows = []
        for vid in workshop.loc[workshop.temp == "reefer", "vehicle_id"]:
            p2 = al.load_problem(*raw, scenario="S1", extra_vehicles=[vid])
            r2 = p2.subset(lambda o: o.temp_requirement == "chilled", lambda v: v.temp == "reefer")
            pl2, _ = al.AllocationModel(r2).solve(al.REEFER_PRIORITIES)
            s2 = pl2[pl2.decision == "served"]
            veh = vehicles.set_index("vehicle_id").loc[vid]
            rows.append({"vehicle_id": vid, "type": veh.type, "m3": veh.volume_cap_m3,
                         "extra_chilled_m3": round(s2.order_volume_m3.sum() - base.order_volume_m3.sum(), 1),
                         "extra_outlets": s2.outlet_id.nunique() - base.outlet_id.nunique()})
        pd.DataFrame(rows).sort_values("extra_chilled_m3", ascending=False).to_csv(OUT / "workshop_repairs.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repairs", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t = task1_bundle()
    task2a_bundle()
    task2b_bundle(args.repairs)
    size = sum(f.stat().st_size for f in OUT.iterdir()) / 1e6
    print(f"bundle written to {OUT}: {len(list(OUT.iterdir()))} files, {size:.1f} MB, {len(t):,} test stops")
