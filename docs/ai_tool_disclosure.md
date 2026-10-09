# AI Tool Disclosure

This disclosure details the use of Artificial Intelligence (AI) assistance in developing the Xora delivery analytics solution for Waypoint Group, in full compliance with the Tech-Triathlon 2026 competition rules and regulations.

---

## 1. Compliance with Competition Rules

Per the Datathon challenge regulations (Challenge Booklet, page 22):
- **Model Restrictions:** No pre-trained model weights (e.g., pre-trained language or computer vision foundation models) were used for final model inference or predictions. All models (LightGBM regressors, classifiers, ElasticNet, and mathematical optimization models) were trained from scratch exclusively on the provided competition datasets.
- **API Usage:** No proprietary, external API-based modeling or feature transformation services (e.g., proprietary LLM inference APIs) were used in the preprocessing, training, or prediction pipelines.
- **No AutoML / Low-Code Modeling Tools:** No automated end-to-end modeling platforms, AutoML tools, or black-box low-code suites were used. The preprocessing pipelines, feature engineering, mathematical optimization formulations, and model architectures were designed and coded by the team.

---

## 2. AI-Assisted Work

AI-based coding assistants (LLMs accessed via the developer IDE) were utilized strictly as interactive pair programmers for the following tasks:

1. **Code Structuring and Boilerplate Generation:**
   - Drafting repetitive DataFrame operations (Pandas merges, aggregations, reshaping).
   - Drafting Matplotlib / Seaborn visualization boilerplate and consistent chart styling (`src/xora/plotting.py`).
   - Drafting helper functions for time parsing and formatting (`src/xora/timeutils.py`).

2. **Refactoring and Linting:**
   - Cleaning up syntax, organizing module structures, and improving modular imports within `src/xora/`.
   - Adding type hints and docstring formatting across shared utility functions.

3. **Documentation Drafting & Formatting:**
   - Formatting markdown tables, summarizing metric tables, and organizing documentation layouts.
   - Proofreading and refining written text for clarity and readability.

4. **Optimization Syntax Validation:**
   - Verifying PuLP constraint declarations and parameter naming syntax when building the integer programming formulation in `src/xora/allocation.py`.

---

## 3. Human-Authored Work (Non-AI Assisted)

All core intellectual contributions, analytical reasoning, and algorithmic logic were developed directly by the team without AI generation:

1. **Problem Framing and Domain Analysis:**
   - Interpreting Waypoint Group's retail logistics constraints: brand priorities (Fresh vs. Style vs. Tech), pre-dawn delivery windows (03:30–08:00 AM), regional depot distribution (Peliyagoda vs. Kandy), and vehicle access restrictions (`van_only`).

2. **Data Wrangling & Label Construction Logic:**
   - Formulating the correct handling time calculation: identifying that vehicles arriving before store opening must wait, and that waiting time outside closed gates is not handling time (`service_start = max(arrival_time, window_open_time)`).
   - Establishing the exact lateness label definition (`arrival_time > window_close_time`).
   - Defining the weekly depot demand aggregation logic, including aligning orders to order request dates, mapping to ISO calendar weeks, isolating chilled demand to Fresh, and adjusting for unserved orders.

3. **Leakage Prevention & Feature Engineering:**
   - Designing the strict 4:00 PM cutoff feature audit to guarantee zero leakage from actual trip execution into training features.
   - Engineering network-specific signals: forward slack along route sequences, dock-type historical priors, festival proximity ramps, and weather disruption indices.

4. **Model Architecture & Strategy:**
   - Formulating the 1,000-run Monte Carlo route simulation algorithm to capture cascading route-level delay propagation.
   - Implementing the dual-model ensemble for Task 2A (harmonic calendar regression + LightGBM GBDT) to handle festival calendar shifts (e.g., Vesak moving between ISO weeks).
   - Designing rolling-origin backtest validation splits.

5. **Task 2B Lexicographical Priority Policy & PuLP Formulation:**
   - Establishing the strict hierarchy of business priorities (repeat deferrals -> chilled volume -> outlet reach -> Fresh ambient -> total volume -> minimizing second pre-dawn trips -> route distance).
   - Developing the two-stage reefer/fleet optimization and computing marginal shadow prices for deferred orders.
   - Formulating the decision layer (risk lights, driver run sheets, store notification templates).

---

## 4. Verification and Audit

All code, data transforms, and model outputs were thoroughly verified by the team:
- Every line of AI-assisted code was manually inspected, reviewed, and audited against raw dataset specifications.
- Optimization outputs were validated against the official `check_allocation.py` script.
- Model performance was evaluated using reproducible holdout splits and rolling cross-validation with pinned random seeds.
