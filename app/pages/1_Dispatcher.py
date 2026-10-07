"""Dispatcher: tomorrow's routes with a light, a reason and a fix for every stop."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import BLUE, ORANGE, SOFT, clock, dl, load, model, paint, page, pill, plotly_layout, tiles

page("Dispatcher risk board", "Task 1 in use",
     "Each stop's late risk blends a route simulation (every route replayed 1,000 times) with a direct classifier. "
     "Red means at least half of such stops run late; amber means one in four.")

test = load("task1_test")
days = sorted(test.date.dt.date.unique())
worst_day = test.groupby(test.date.dt.date).pred_late_prob.mean().idxmax()

f = st.columns([1.2, 1, 1, 2])
day = f[0].selectbox("Delivery day", days, index=days.index(worst_day), format_func=lambda d: d.strftime("%a %d %b %Y"))
depot = f[1].selectbox("Depot", ["All"] + sorted(test.depot.unique()))
brand = f[2].selectbox("Brand", ["All"] + sorted(test.brand.unique()))

d = test[test.date.dt.date == day]
if depot != "All":
    d = d[d.depot == depot]
if brand != "All":
    d = d[d.brand == brand]
d = d.sort_values(["route_id", "seq"])

counts = d.light.value_counts()
red_share = d.loc[d.light == "red", "pred_late_prob"].sum() / max(d.pred_late_prob.sum(), 1e-9)
tiles([("Routes", d.route_id.nunique(), f"{len(d)} stops"),
       ("Red stops", int(counts.get("red", 0)), f"{red_share:.0%} of expected late arrivals", "#b03030"),
       ("Amber stops", int(counts.get("amber", 0)), "driver calls ahead if behind", "#8a5d00"),
       ("Expected late arrivals", f"{d.pred_late_prob.sum():.0f}", f"out of {len(d)} stops")])

# One row per route, worst first
board = []
for rid, g in d.groupby("route_id"):
    worst = g.loc[g.pred_late_prob.idxmax()]
    board.append({"route": rid, "brand": g.brand.iloc[0], "district": g.district.iloc[0], "leaves": clock(g.route_start_min.iloc[0]),
                  "stops": len(g), "red": int((g.light == "red").sum()), "amber": int((g.light == "amber").sum()),
                  "worst stop": f"stop {int(worst.seq) + 1} ({worst.outlet_id})" if worst.light != "green" else "",
                  "why": worst.reason, "suggested fix": dl.route_fix(g)})
board = pd.DataFrame(board)
board["light"] = np.where(board.red > 0, "red", np.where(board.amber > 0, "amber", "green"))
board = board.sort_values(["red", "amber"], ascending=False).reset_index(drop=True)

st.markdown("#### Routes, riskiest first")
st.dataframe(paint(board), hide_index=True, use_container_width=True, height=300,
             column_order=["light", "route", "brand", "district", "leaves", "stops", "red", "amber", "worst stop", "why", "suggested fix"])

st.markdown("#### Route detail")
route = st.selectbox("Route", board.route, format_func=lambda r: f"{r}  ({board.set_index('route').at[r, 'light']}, "
                     f"{board.set_index('route').at[r, 'district']}, leaves {board.set_index('route').at[r, 'leaves']})")
r = d[d.route_id == route].sort_values("seq")

left, right = st.columns([1.35, 1])
with left:
    sheet = pd.DataFrame({
        "stop": r.seq.astype(int) + 1, "outlet": r.outlet_id,
        "window": [f"{clock(a)} to {clock(b)}" for a, b in zip(r.window_open_time_min, r.window_close_time_min)],
        "planned": r.planned_arrival_min.map(clock),
        "likely arrival": [dl.arrival_range(a, b) for a, b in zip(r.arrival_p50_min, r.arrival_p90_min)],
        "unloading": [f"about {5 * max(1, round(x / 5))} min" for x in r.pred_service_min],
        "late risk": (r.pred_late_prob * 100).round(0).astype(int).astype(str) + "%",
        "light": r.light, "why": r.reason,
    })
    st.dataframe(paint(sheet), hide_index=True, use_container_width=True)
    st.markdown(f"**Suggested fix:** {dl.route_fix(r)}")
with right:
    st.markdown("**Messages to stores, sent the evening before**")
    for x in r.itertuples():
        st.markdown(f'<div class="msg">{pill(x.light)} <b>{x.outlet_id}</b><br>{dl.store_message(x)}</div>', unsafe_allow_html=True)

# What-if: the simulator is fast enough to replay a route live
st.markdown("#### What if the truck leaves earlier?")
st.caption("Replays this route 1,000 times with the saved route simulator. Arriving before a store opens just means waiting, "
           "so leaving earlier only helps where the window is the problem.")
shift = st.slider("Leave earlier by (minutes)", 0, 120, 0, step=15)
sim = model("route_simulator.pkl")
base = sim.simulate(r).set_index("delivery_id").reindex(r.delivery_id)
moved = r.copy()
moved["planned_depart_time_min"] = moved.planned_depart_time_min - shift
new = sim.simulate(moved).set_index("delivery_id").reindex(r.delivery_id)

k = st.columns(3)
k[0].metric("Leaves the depot", clock(r.route_start_min.iloc[0] - shift), f"-{shift} min" if shift else None, delta_color="off")
lights_before = base.sim_late_prob.map(dl.light).value_counts().get("red", 0)
lights_after = new.sim_late_prob.map(dl.light).value_counts().get("red", 0)
k[1].metric("Red stops (simulation)", int(lights_after), int(lights_after - lights_before) if shift else None, delta_color="inverse")
k[2].metric("Expected late arrivals (simulation)", f"{new.sim_late_prob.sum():.1f}",
            f"{new.sim_late_prob.sum() - base.sim_late_prob.sum():+.1f}" if shift else None, delta_color="inverse")

x = [f"stop {i + 1}" for i in r.seq.astype(int)]
fig = go.Figure()
fig.add_trace(go.Scatter(x=x + x[::-1], y=list(new.arrival_p90_min) + list(new.arrival_p50_min)[::-1], fill="toself",
                         fillcolor="rgba(42,120,214,0.18)", line=dict(width=0), name="likely arrival range", hoverinfo="skip"))
fig.add_trace(go.Scatter(x=x, y=new.arrival_p50_min, mode="lines+markers", line=dict(color=BLUE, width=3), marker=dict(size=9),
                         name="likely arrival", customdata=[clock(v) for v in new.arrival_p50_min],
                         hovertemplate="%{x}: about %{customdata}<extra></extra>"))
if shift:
    fig.add_trace(go.Scatter(x=x, y=base.arrival_p50_min, mode="lines", line=dict(color=SOFT, width=2, dash="dot"),
                             name="likely arrival before the change", hoverinfo="skip"))
fig.add_trace(go.Scatter(x=x, y=r.window_close_time_min, mode="markers", marker=dict(symbol="line-ew-open", size=26, color=ORANGE,
                         line=dict(width=3)), name="window closes", customdata=[clock(v) for v in r.window_close_time_min],
                         hovertemplate="%{x}: closes %{customdata}<extra></extra>"))
lo = min(new.arrival_p50_min.min(), r.window_open_time_min.min()) - 20
hi = max(new.arrival_p90_min.max(), base.arrival_p50_min.max(), r.window_close_time_min.max()) + 20
ticks = list(range(int(lo // 30 * 30), int(hi) + 30, 30))
fig.update_yaxes(tickvals=ticks, ticktext=[clock(t) for t in ticks], range=[lo, hi], title=None)
st.plotly_chart(plotly_layout(fig, 400), use_container_width=True)
