"""Peak-day planner: the S1 allocation, every deferral explained, and what a workshop repair is worth."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import BLUE, DATA, GREEN, SOFT, load, page, plotly_layout, tiles

page("Peak-day plan", "Task 2B in use",
     "Scenario S1 at Peliyagoda: a peak day before a festival with ten vehicles in the workshop. The optimiser solves "
     "Waypoint's priorities strictly in order, so a lower priority can never win at the expense of a higher one.")

plan, trips = load("task2b_plan"), load("task2b_trips")
served = plan[plan.decision == "served"]
chilled = plan[plan.temp_requirement == "chilled"]

tiles([("Orders served", f"{len(served)} of {len(plan)}", f"{served.order_volume_m3.sum():.0f} of {plan.order_volume_m3.sum():.0f} m3", BLUE),
       ("Repeat deferrals served", f"{int(served.deferred_yesterday.sum())} of {int(plan.deferred_yesterday.sum())}", "no store waits two days in a row", GREEN),
       ("Chilled served", f"{served[served.temp_requirement == 'chilled'].order_volume_m3.sum():.1f} m3",
        f"of {chilled.order_volume_m3.sum():.0f} m3, the most any plan can serve", BLUE),
       ("Trips", len(trips), f"{trips.km.sum():,.0f} km in total")])
st.write("")
st.markdown("#### Priorities, in this order")
st.markdown("1. No outlet waits two days in a row  \n2. Chilled goods (up to 1% of the best chilled volume may be traded to reach more stores)  \n"
            "3. Fresh ambient before opening  \n4. Total volume  \n5. Fewest second pre-dawn trips  \n6. Fewest kilometres")

tab = st.tabs(["Trips", "Deferrals", "Loading sheets", "Late warnings", "Workshop repairs"])

with tab[0]:
    t = trips.sort_values(["vehicle_id", "trip_id"])
    fig = go.Figure(go.Bar(x=t.volume_fill * 100, y=t.vehicle_id + " trip " + t.trip_id.astype(str), orientation="h",
                           marker_color=[BLUE if c else GREEN for c in t.temp.eq("reefer")],
                           hovertemplate="%{y}: %{x:.0f}% full<extra></extra>"))
    fig.update_xaxes(title="volume used (%)", range=[0, 105])
    fig.update_layout(title=dict(text="How full each trip is (blue: reefer, green: ambient)", x=0, font=dict(size=16)))
    st.plotly_chart(plotly_layout(fig, max(320, 22 * len(t))), use_container_width=True)
    st.dataframe(pd.DataFrame({
        "vehicle": t.vehicle_id, "trip": t.trip_id, "kind": t.temp + " " + t.type, "brand": t.brand, "district": t.district,
        "orders": t.orders, "m3": [f"{a:.1f} of {b:.1f}" for a, b in zip(t.volume_m3, t.volume_cap_m3)],
        "kg": [f"{a:,.0f} of {b:,.0f}" for a, b in zip(t.weight_kg, t.weight_cap_kg)],
        "planned min": t.planned_min, "km": t.km.round(0).astype(int)}), hide_index=True, use_container_width=True)

with tab[1]:
    st.caption("Every deferral has a reason code and a price: what serving it instead would cost other stores.")
    st.dataframe(load("peak_day_deferral_list"), hide_index=True, use_container_width=True)
    st.markdown("**Notices to the stores**")
    for x in load("peak_day_store_notices").itertuples():
        st.markdown(f'<div class="msg"><b>{x.outlet}</b><br>{x.message}</div>', unsafe_allow_html=True)

with tab[2]:
    s = load("peak_day_loading_sheets")
    keys = s[["vehicle_id", "trip_id"]].drop_duplicates().sort_values(["vehicle_id", "trip_id"])
    pick = st.selectbox("Trip", [f"{v} trip {t}" for v, t in zip(keys.vehicle_id, keys.trip_id)])
    v, t = pick.split(" trip ")
    one = s[(s.vehicle_id == v) & (s.trip_id == int(t))].sort_values("load_order")
    st.caption(f"Load in this order: the last stop goes in first, so the first stop is at the doors. Trip fill: {one.trip_fill.iloc[0]}.")
    st.dataframe(one.drop(columns=["vehicle_id", "trip_id", "trip_fill"]), hide_index=True, use_container_width=True)

with tab[3]:
    st.caption("Replayed on the clock, these second pre-dawn reefer runs reach stores after opening. The stores hear about it the evening before.")
    st.dataframe(load("peak_day_late_warnings"), hide_index=True, use_container_width=True)

with tab[4]:
    if (DATA / "workshop_repairs.csv").exists():
        rep = load("workshop_repairs").sort_values("extra_chilled_m3")
        fig = go.Figure(go.Bar(x=rep.extra_chilled_m3, y=rep.vehicle_id + " (" + rep.type + ", " + rep.m3.astype(str) + " m3)",
                               orientation="h", marker_color=BLUE, text=[f"+{v:.1f} m3, +{int(o)} stores" for v, o in zip(rep.extra_chilled_m3, rep.extra_outlets)],
                               textposition="outside", textfont=dict(color=SOFT)))
        fig.update_xaxes(title="extra chilled volume served if this reefer is back for the morning (m3)", range=[0, rep.extra_chilled_m3.max() * 1.3])
        fig.update_layout(title=dict(text="Which reefer should the workshop release first?", x=0, font=dict(size=16)))
        st.plotly_chart(plotly_layout(fig, 340), use_container_width=True)
        st.caption("Each bar is a full re-solve with that vehicle added back. A large reefer truck recovers most of the chilled deferrals; "
                   "the reefer van recovers less volume but is the only way to reach van-only outlets with chilled goods.")
    else:
        st.info("Run `python app/build_app_data.py --repairs` to add the workshop ranking.")
