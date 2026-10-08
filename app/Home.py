"""Xora planning app: the models and plans from the notebooks, in the hands of the people who use them.

Run from the repo root:  streamlit run app/Home.py
"""

import streamlit as st

from common import BLUE, ROOT, load, manifest, page, tiles

page("Smarter delivery planning for Waypoint Group", "Xora",
     "Every number here comes from the saved models and outputs in this repo. Pick a page on the left, or start below.")

m = manifest()
t1, t2 = m["task1"]["holdout"], m["task2a"]["backtest_blend"]
plan = load("task2b_plan")
served = plan[plan.decision == "served"]

tiles([
    ("Service time error per stop", f"{t1['service']['MAE']:.1f} min", f"allowance table today: {t1['allowance_table_MAE']:.1f} min", BLUE),
    ("Late risk AUC", f"{t1['late']['AUC']:.2f}", f"log loss {t1['late']['log loss']:.3f}, slack rule 0.287", BLUE),
    ("Weekly volume error", f"{t2['total']['WAPE']:.1%}", f"{1 - t2['total']['vs last year']:.0%} less than copying last year", BLUE),
    ("Peak-day orders served", f"{len(served)} of {len(plan)}",
     f"all {int(plan.deferred_yesterday.sum())} repeat deferrals ride", BLUE),
])
st.write("")
st.markdown("#### What each person gets")
roles = [
    ("Dispatcher", "A risk board for tomorrow's routes: every stop gets a light, a reason and a fix. Try moving a departure and watch the risk change.", "pages/1_Dispatcher.py", "Open the risk board"),
    ("Fleet manager", "Ten weeks of total and chilled volume per depot and brand, with ranges, and the weeks when every reefer must stay on the road.", "pages/2_Demand_outlook.py", "Open the demand outlook"),
    ("Peak-day planner", "Who rides and who waits when the fleet is short, with a reason and a price for every deferral, and loading sheets.", "pages/3_Peak_day.py", "Open the peak-day plan"),
    ("Anyone checking the work", "Reload the saved models and reproduce the submission files on the spot.", "pages/4_Model_check.py", "Open the model check"),
]
cols = st.columns(4)
for col, (who, what, link, label) in zip(cols, roles):
    with col:
        st.markdown(f'<div class="card"><h4>{who}</h4><p>{what}</p></div>', unsafe_allow_html=True)
        st.page_link(link, label=label)

st.write("")
st.markdown("#### How it fits together")
st.image(str(ROOT / "docs" / "figures" / "architecture_pipeline.png"), width="stretch")
st.caption("Full workings, from raw files to these outputs, are in `Xora_FinalNotebook.ipynb`.")
