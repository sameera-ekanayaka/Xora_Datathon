"""Anyone checking the work: reload the saved models and reproduce the submissions."""

import time

import numpy as np
import pandas as pd
import streamlit as st

from common import ROOT, load, manifest, model, page

page("Model check", "Reproducibility",
     "The models are versioned files in `models/`, listed in `models/manifest.json` with their training window, seed and holdout scores.")

m = manifest()
t1, t2 = m["task1"], m["task2a"]
c = st.columns(2)
with c[0]:
    st.markdown("#### Task 1: service time and late risk")
    st.dataframe(pd.DataFrame({
        "measure": ["service time MAE (min)", "service time RMSE (min)", "late risk log loss", "late risk Brier", "late risk AUC"],
        "ours": [t1["holdout"]["service"]["MAE"], t1["holdout"]["service"]["RMSE"], t1["holdout"]["late"]["log loss"],
                 t1["holdout"]["late"]["Brier"], t1["holdout"]["late"]["AUC"]],
        "today": [t1["holdout"]["allowance_table_MAE"], None, 0.287, None, 0.86],
    }).round(3), hide_index=True, width="stretch")
    st.caption(f"Trained on {t1['trained_on']}. {t1['simulation_runs']:,} simulated runs per route, seed {t1['seed']}. "
               f"Late risk: {t1['late_risk']}.")
with c[1]:
    st.markdown("#### Task 2A: weekly volume")
    b = t2["backtest_blend"]
    st.dataframe(pd.DataFrame({
        "measure": ["weekly error (WAPE)", "error vs same week last year", "bias"],
        "total": [f"{b['total']['WAPE']:.1%}", f"{b['total']['vs last year']:.0%}", f"{b['total']['bias']:+.1%}"],
        "chilled": [f"{b['chilled']['WAPE']:.1%}", f"{b['chilled']['vs last year']:.0%}", f"{b['chilled']['bias']:+.1%}"],
    }), hide_index=True, width="stretch")
    st.caption(f"{t2['method'].capitalize()}. Trained on {t2['trained_on']}; P10 to P90 ranges cover "
               f"{t2['interval_coverage_leave_one_out']:.0%} of backtest weeks.")

st.markdown("#### Reproduce the Task 1 submission now")
st.caption("Reloads both Task 1 models from disk, replays all 5,014 test stops and compares with `submissions/submission_task1.csv`.")
if st.button("Run Task 1 inference", type="primary"):
    test = load("task1_test")
    start = time.time()
    with st.spinner("Replaying every test route 1,000 times..."):
        sim = model("route_simulator.pkl").simulate(test)
        clf = model("late_classifier.pkl")
        p = np.clip((sim.sim_late_prob.to_numpy() + clf.predict_proba(test[clf.feature_name_])[:, 1]) / 2, 0.002, 0.998)
    out = pd.DataFrame({"delivery_id": test.delivery_id, "pred_service_min": sim.pred_service_min.round(2), "pred_late_prob": p.round(4)})
    sub = pd.read_csv(ROOT / "submissions" / "submission_task1.csv").set_index("delivery_id").reindex(out.delivery_id)
    k = st.columns(3)
    k[0].metric("Stops scored", f"{len(out):,}", f"in {time.time() - start:.1f} s", delta_color="off")
    k[1].metric("Largest service difference", f"{np.abs(out.pred_service_min.to_numpy() - sub.pred_service_min.to_numpy()).max():.3f} min")
    k[2].metric("Largest late-risk difference", f"{np.abs(out.pred_late_prob.to_numpy() - sub.pred_late_prob.to_numpy()).max():.4f}")
    st.dataframe(out.head(10), hide_index=True, width="stretch")

st.markdown("#### Task 2B feasibility")
st.code("python check_allocation.py submissions/submission_task2b.csv\nFEASIBILITY: PASSED - every rule satisfied.", language="text")
st.caption("Output of Waypoint's own checker on the committed plan, as rerun in Part 11 of the final notebook.")
