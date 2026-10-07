"""Fleet manager: the 10-week volume outlook and the reefer maintenance calendar."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import BLUE, SOFT, load, manifest, paint, page, plotly_layout, tiles

page("Demand outlook", "Task 2A in use",
     "Forecasts are made per day, so festivals land in the right 2026 week, then added up into ISO weeks. "
     "The band runs from P10 to P90.")

fc, hist, fest = load("task2a_forecast"), load("weekly_history"), load("festival_weeks")
f = st.columns([1, 1, 1, 2])
depot = f[0].selectbox("Depot", sorted(fc.depot.unique()), index=sorted(fc.depot.unique()).index("Peliyagoda"))
brand = f[1].selectbox("Brand", ["Fresh", "Style", "Tech"])
measure = f[2].radio("Volume", ["total", "chilled"] if brand == "Fresh" else ["total"], horizontal=True)

h = hist[(hist.depot == depot) & (hist.brand == brand)].copy()
h["week"] = pd.to_datetime(h.iso_year.astype(str) + "-W" + h.iso_week.astype(str).str.zfill(2) + "-1", format="%G-W%V-%u")
h = h[h.week >= "2025-01-01"]
g = fc[(fc.depot == depot) & (fc.brand == brand) & (fc.measure == measure)].copy()
g["week"] = pd.to_datetime(g.iso_year.astype(str) + "-W" + g.iso_week.astype(str).str.zfill(2) + "-1", format="%G-W%V-%u")
g = g.merge(fest, on=["iso_year", "iso_week"], how="left")

same = h[(h.iso_year == 2025) & h.iso_week.isin(g.iso_week)][measure].sum()
peak = g.loc[g.p50.idxmax()]
tiles([("Next 10 weeks, P50", f"{g.p50.sum():,.0f} m3", f"P10 {g.p10.sum():,.0f} to P90 {g.p90.sum():,.0f} m3", BLUE),
       ("Busiest week", f"week {int(peak.iso_week)}", f"{peak.p50:,.0f} m3" + (f", {peak.festival.replace('_', ' ')}" if isinstance(peak.festival, str) else "")),
       ("Against the same weeks of 2025", f"{g.p50.sum() / same - 1:+.0%}" if same else "n/a", "festival weeks moved, so weekly shapes differ")])

fig = go.Figure()
fig.add_trace(go.Scatter(x=h.week, y=h[measure], mode="lines", line=dict(color=SOFT, width=1.6), name="actual"))
fig.add_trace(go.Scatter(x=list(g.week) + list(g.week)[::-1], y=list(g.p90) + list(g.p10)[::-1], fill="toself",
                         fillcolor="rgba(42,120,214,0.18)", line=dict(width=0), name="P10 to P90", hoverinfo="skip"))
fig.add_trace(go.Scatter(x=g.week, y=g.p50, mode="lines+markers", line=dict(color=BLUE, width=3), marker=dict(size=7),
                         name="forecast P50", customdata=g[["iso_week", "p10", "p90"]],
                         hovertemplate="week %{customdata[0]}: %{y:,.0f} m3 (P10 %{customdata[1]:,.0f}, P90 %{customdata[2]:,.0f})<extra></extra>"))
for w in g.dropna(subset=["festival"]).itertuples():
    fig.add_annotation(x=w.week, y=w.p90, text=w.festival.replace("_", " "), showarrow=False, yshift=14,
                       font=dict(size=12, color=SOFT))
fig.update_layout(title=dict(text=f"{depot} {brand}, {measure} volume per ISO week (m3)", x=0, font=dict(size=16)))
st.plotly_chart(plotly_layout(fig, 430), width="stretch")

st.markdown("#### Reefer outlook: when to book maintenance")
st.caption("Chilled volume per operating day against the depot's own busiest days so far. "
           "Red weeks are busier than 95% of the days the depot has ever run.")
o = load("reefer_outlook")
show = pd.DataFrame({
    "light": o.status, "depot": o.depot, "week": o.iso_week, "operating days": o.operating_days,
    "chilled m3 a day": [f"{a:.0f} to {b:.0f}" for a, b in zip(o.m3_per_day_p50, o.m3_per_day_p90)],
    "reefer trips a day": [f"{a:.0f} to {b:.0f}" for a, b in zip(o.trips_per_day_p50, o.trips_per_day_p90)],
    "busiest days so far": [f"{a:.0f} to {b:.0f}" for a, b in zip(o.busy_day_p90, o.busy_day_p95)],
    "advice": o.advice,
})
which = st.radio("Show", ["Both depots", "Kandy", "Peliyagoda"], horizontal=True, label_visibility="collapsed")
if which != "Both depots":
    show = show[show.depot == which]
st.dataframe(paint(show), hide_index=True, width="stretch")

b = manifest()["task2a"]["backtest_blend"]
st.caption(f"Backtests over six 10-week windows: weekly error {b['total']['WAPE']:.1%} on total and {b['chilled']['WAPE']:.1%} on chilled, "
           f"{1 - b['total']['vs last year']:.0%} and {1 - b['chilled']['vs last year']:.0%} less than copying the same week last year.")
