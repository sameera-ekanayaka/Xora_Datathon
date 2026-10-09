# Data Preprocessing and Model Cards

This document details the data preparation, data cleaning, label construction, feature engineering methodology, and model architectures for the Waypoint Group delivery analytics system.

---

## 1. Overview & Data Ingestion

The solution ingests synthetic operational data from 11 core files across two depots (Peliyagoda and Kandy), serving 120 retail outlets with 60 vehicles across three brands (**Fresh**, **Style**, and **Tech**):

- **Order Records:** `deliveries_train.csv` (92,307 historical training orders) and `task1_test_inputs.csv` (5,014 test orders; 97,321 orders total).
- **Route Execution Legs:** `route_legs_train.csv` (91,894 training legs) and `route_legs_test.csv` (5,014 planned legs; 96,908 legs total).
- **Network Reference:** `outlets.csv` (120 outlets), `vehicles.csv` (60 vehicles), `district_travel.csv` (12 districts), `service_allowance.csv` (9 brand/dock combinations).
- **Operating Context:** `calendar.csv` (910 operating/calendar days), `traffic_speed.csv` (congestion by district and hour), `road_conditions.csv` (disruption index).

### Data Ingestion and Unification Pipeline
1. **Clock Time Conversion:** All timestamps ending in `_time` (formatted as `HH:MM`) are parsed into scalar integers representing minutes from midnight ($0 \le t < 1440$) using `xora.timeutils.hhmm_to_minutes`.
2. **Order-to-Leg Linking:** Dispatched orders in `deliveries_train.csv` and `task1_test_inputs.csv` match exactly one leg in the route table where `(route_id, seq_in_route)` equals `(route_id, seq)`. Orders and route legs are combined into a unified analysis table (`stops.parquet`).
3. **Partition Tracking:** A strict `split` column (`train` vs `test`) is maintained throughout the pipeline to prevent cross-contamination.

---

## 2. Data Quality and Cleaning

The data cleaning pipeline (`notebooks/02_data_quality_and_cleaning.ipynb`) applies programmatic sanity checks across all tables:

### Structural and Domain Rule Checks
- **Primary Keys:** Confirmed 100% uniqueness of `delivery_id` in orders, `leg_id` in route legs, and `outlet_id` in outlets.
- **Categorical Integrity:** Validated allowed values for brands (`Fresh`, `Style`, `Tech`), depots (`Peliyagoda`, `Kandy`), temperature requirement (`chilled`, `ambient`), and dispatch statuses (`attempted`, `deferred`, `not_run`).
- **Operating Days:** Confirmed that day-of-week (`dow`) is strictly between 0 (Monday) and 5 (Saturday), as Waypoint does not operate Sunday deliveries.

### Missing Values and Blank Handling
- **Route Attributes for `not_run` Orders:** Out of 92,307 training orders, exactly 413 have `dispatch_status == 'not_run'`. These orders have null route and execution fields because they were never dispatched due to depot capacity shortages.
  - *Treatment:* They are retained in the master order table to ensure full demand accounting for Task 2A (where every customer order represents genuine demand), but excluded from Task 1 route service and lateness modeling.
- **Zero Inconsistencies:** No missing values exist in network reference tables or test inputs.

### Cross-Table Referential Consistency
- Confirmed that redundant outlet attributes present in order records (`brand`, `district`, `depot`, `window_open_time`, `window_close_time`) match `outlets.csv` with zero discrepancies.
- Confirmed that vehicle attributes (`vehicle_type`, `vehicle_temp`) match `vehicles.csv`.

---

## 3. Label Construction

Neither Task 1 target is supplied in the raw inputs. Both are derived from route execution records following the operational specifications in the Challenge Booklet (`notebooks/03_label_construction.ipynb`).

### 3.1 Outlet Handling / Service Time (`pred_service_min`)
- **Operational Requirement:** Outlets receive goods only during their scheduled delivery window (`window_open_time` to `window_close_time`). A vehicle arriving early must wait until the store opens. Time spent idling outside a closed outlet is gate waiting time, not handling time.
- **Mathematical Formulation:**
  $$\text{service\_start} = \max(\text{arrival\_time\_min}, \text{window\_open\_time\_min})$$
  $$\text{service\_min} = \text{leave\_outlet\_time\_min} - \text{service\_start}$$
  $$\text{wait\_min} = \text{service\_start} - \text{arrival\_time\_min}$$
- **Verification:**
  - If calculated simply as $\text{leave} - \text{arrival}$, first stops (which often arrive before store opening) would appear falsely prolonged by 15–45 minutes of idle waiting.
  - The derived `service_min` accurately isolates handling: Fresh has a median handling time of ~15 minutes; Style medians are 30–61 minutes; Tech medians are 35–74 minutes depending on dock type (`rear_dock`, `street`, `mall_bay`).

### 3.2 Lateness Probability (`pred_late_prob`)
- **Operational Requirement:** Lateness refers strictly to arrival after the outlet's delivery window has closed. Late deliveries are still accepted and unloaded.
- **Mathematical Formulation:**
  $$\text{late} = \begin{cases} 1, & \text{if } \text{arrival\_time\_min} > \text{window\_close\_time\_min} \\ 0, & \text{otherwise} \end{cases}$$
- **Boundary Handling:** Arriving exactly at `window_close_time_min` is classified as on-time ($0$).
- **Distribution:** Across training routes, ~20.9% of deliveries arrive late, heavily concentrated on Fresh pre-dawn routes where tight 8:00 AM cutoffs interact with road congestion.

### 3.3 Weekly Depot Demand Construction (Task 2A)
- **Aggregation Rules:**
  1. Every order is counted once, including deferred orders and `not_run` orders, as all represent customer demand.
  2. Orders are assigned to the week corresponding to their **requested `order_date`**, rather than actual dispatch date.
  3. Grouping uses `iso_year` and `iso_week` from `calendar.csv`.
- **Gap Adjustment:** The gap between the training set (ending 2026 week 7) and test forecast horizon (weeks 14 to 23) is bridged using `task1_test_inputs.csv` (weeks 8 to 13), adjusted for the small historical proportion of undispatched orders (`not_run_uplift`).
- **Chilled Isolation:** Chilled demand is strictly zeroed for Style and Tech (`pred_chilled_volume_m3 = 0.0`), as only Fresh handles refrigerated goods.

---

## 4. Feature Engineering & 4:00 PM Cutoff Audit

All features used for Task 1 modeling are verified against `reports/feature_audit.csv` and aligned with the operational boundary at the **4:00 PM cutoff** before the delivery day (`notebooks/04_feature_engineering.ipynb`).

A total of **61 features** are constructed, grouped identically to `reports/feature_audit.csv`:

| Feature Group | Count | Key Features | Operational Rationale | Cutoff Status |
|---|---|---|---|---|
| **Route position** | 21 | `seq`, `is_first_stop`, `route_n_stops`, `stops_after`, `same_outlet_as_previous`, `route_volume_m3`, `route_weight_kg`, `volume_before_m3`, `route_distance_km`, `distance_so_far_km`, `leg_distance_km`, `planned_travel_min`, `planned_travel_so_far_min`, `route_start_min`, `planned_arrival_min`, `planned_hour`, `minutes_into_route`, `window_length_min`, `planned_slack_min`, `planned_early_min`, `min_slack_ahead_min` | Encodes sequence in the drafted route, cumulative drive times, and forward buffer margins. | Available at 4 PM (from drafted route legs) |
| **Order and vehicle** | 19 | `brand`, `depot`, `district`, `temp_requirement`, `dock_type`, `parking_constraint`, `vehicle_type`, `vehicle_temp`, `outlet_id`, `order_units`, `order_weight_kg`, `order_volume_m3`, `kg_per_unit`, `is_chilled`, `is_mall`, `was_deferred`, `vehicle_volume_cap_m3`, `vehicle_weight_cap_kg`, `allowance_min` | Physical characteristics of the delivery, dock access constraints, vehicle capacity, and standard allowance. | Available at 4 PM (confirmed order + plan) |
| **Calendar** | 9 | `dow`, `month`, `is_payday`, `is_holiday`, `monsoon`, `festival_ramp`, `is_festival_day`, `days_to_festival`, `trend_days` | Day of week, seasonal shifts, monsoon indicators, and holiday / payday shopping surges. | Available at 4 PM (known calendar) |
| **History** | 6 | `group_hist_service_mean`, `outlet_hist_stops`, `outlet_hist_service_mean`, `outlet_hist_late_rate`, `district_hist_travel_ratio`, `vehicle_hist_depart_delay` | Historical performance priors computed strictly on dates preceding the delivery day ($t-1$). | Available at 4 PM (prior route logs) |
| **Plan combined with history** | 4 | `load_share_volume`, `load_share_weight`, `expected_travel_min`, `slack_after_history_min` | Blends planned metrics with historical driver and district speed ratios. | Available at 4 PM (computed before dispatch) |
| **Road and traffic** | 2 | `disruption_index`, `speed_index` | Hourly district congestion index and road disruption advisory index. | See advisory note below |

### 4:00 PM Cutoff and Road Advisory Audit
- **Strictly Known Features (60 / 61):** 60 features are strictly known when the planner drafts the next day's run sheets at 4:00 PM. No downstream execution timestamps (`actual_depart_time_min`, `actual_travel_duration_min`, `arrival_time_min`, `leave_outlet_time_min`) leak into any feature.
- **Borderline Feature (`disruption_index`):** As documented in `reports/feature_audit.csv`, `disruption_index` is classified as **borderline** because in production it represents a published road advisory / disruption notice available ahead of the run. Models were trained and validated both with and without this feature; because it improves late risk calibration without introducing post-event leakage, `manifest.json` confirms `road_advisory_used: true`.
- **Deployment Dependency and Fallback:** The final late-risk models use `disruption_index`, a published road advisory. It must reach the planner by 4 PM. If it is missing, use the no-advisory fallback: holdout log loss 0.174, AUC 0.957, service MAE 3.98, against 0.136, 0.974, and 3.92 with it. The fallback models can be retrained directly from notebook cell 154 (`notebooks/05_task1_service_and_lateness.ipynb` and `Xora_FinalNotebook.ipynb`).

---

## 5. Model Cards

All production models are serialized in `models/` alongside configuration metadata in `models/manifest.json`.

### Model 1: Task 1 Service Time Regressor
- **Architecture:** LightGBM Gradient Boosted Regressor (`models/route_simulator.pkl` regression component).
- **Objective:** Mean (L2), chosen after comparing median, mean, and Huber loss objectives.
- **Inputs:** 61 cutoff-time features.
- **Holdout Performance:**
  - **MAE:** **3.92 minutes** (compared to the baseline published allowance table MAE of **7.09 minutes** — a **45% error reduction**).
  - **RMSE:** 6.30 minutes.
  - **Mean Bias:** +0.23 minutes (unbiased).

### Model 2: Task 1 Arrival Lateness Predictor
- **Architecture:** 50/50 Ensemble of:
  1. **Route Simulator (Monte Carlo Engine):** 1,000 stochastic route-level replays sampling travel time ratios, handling variations, and depot departure delays to capture non-linear cascading lateness across stops.
  2. **Direct Classifier:** LightGBM Binary Classifier trained with binary cross-entropy on stop features (`models/late_classifier.pkl`).
- **Holdout Performance:**
  - **ROC-AUC:** **0.9745** (substantially outperforming paper slack baseline AUC of 0.86).
  - **Log Loss:** **0.1360** (vs baseline 0.287).
  - **Brier Score:** **0.0415**, a measure of probability error. Calibration is checked separately with a holdout reliability plot and predicted-against-observed late share by stop position (notebook sections 6.6 and 6.8). Predictions track observed rates closely, with small over-prediction at some stop positions.

### Model 3: Task 2A Weekly Depot Demand Forecaster
- **Architecture:** Daily forecasting aggregated into ISO calendar weeks:
  1. **Trend Regression:** Per-series ridge regression on log volume with growth trend (`t_years`), day-of-week and month indicators, and calendar flags (`festival_ramp`, `is_payday`, `is_holiday`, `monsoon`, `pre_festival`, `post_festival`) fitted on operating days (`models/demand_regression.pkl`).
  2. **Calendar LightGBM Regressor:** One LightGBM across all series that learns non-linear calendar effects and festival timing on top of the regression growth trend (`models/demand_calendar_gbm.pkl`).
- **Methodology:** Daily volume is predicted per depot, brand, and temperature measure, then summed by `iso_year` and `iso_week` to ensure moveable holidays (such as Vesak moving between ISO weeks 18, 20, and 21) are placed accurately without artificial week-matching errors.
- **Backtest Validation (6 Rolling Origins across 2025–2026):**
  - **Total Volume WAPE:** **5.16%** (**41% lower error** than a baseline of about 8.7% based on same week last year; ratio vs last year is 0.591).
  - **Chilled Volume WAPE:** **3.62%** (**54% lower error** than last year's baseline of 7.8%; ratio vs last year is 0.463).
  - **Prediction Interval Coverage:** The P10 to P90 band covers about 76% of held-out weeks (target 80%), so it is slightly narrow. We did not recalibrate it.

### Model 4: Task 2B Peak-Day Fleet Allocator
- **Architecture:** Mixed-Integer Linear Program (MILP) formulated in PuLP and solved via CBC (`src/xora/allocation.py`).
- **Algorithm:** Strict lexicographic multi-objective optimization across 6 locked priority tiers:
  1. Priority 1: Serve 100% of orders deferred on previous runs.
  2. Priority 2: Maximize chilled volume served (allowing $\le 1\%$ trade-off to maximize number of distinct outlets reached).
  3. Priority 3: Maximize Fresh ambient volume (shelves stocked before 8:00 AM).
  4. Priority 4: Maximize total delivered volume across Style and Tech.
  5. Priority 5: Minimize high-risk second pre-dawn trips.
  6. Priority 6: Minimize total fleet kilometers.
- **Result:** Serves 76 of 85 orders (320.161 of 409.866 $\text{m}^3$), all 10 orders with `deferred_yesterday == 1` served (this does not guarantee two-day service for all outlets, as 4 deferred orders have 2 days since last served and S1-078 requires splitting), 18 of 26 chilled outlets (132.586 $\text{m}^3$ vs proven strict maximum of 132.833 $\text{m}^3$), fully validated by `check_allocation.py`.
