# AI Tool Disclosure

This disclosure details the use of Artificial Intelligence (AI) assistance in developing the Xora delivery analytics solution for Waypoint Group, in full compliance with the Tech-Triathlon 2026 competition rules and regulations.

---

## 1. Compliance with Competition Rules

Per the Datathon challenge regulations (Challenge Booklet, page 22):
- **Model Restrictions:** No pre-trained model weights (e.g., pre-trained language or computer vision foundation models) were used for final model inference or predictions. All models (LightGBM regressors, classifiers, ridge regressors, and mathematical optimization models) were trained from scratch exclusively on the provided competition datasets.
- **API Usage:** No proprietary, external API-based modeling or feature transformation services (e.g., proprietary LLM inference APIs) were used in the preprocessing, training, or prediction pipelines.
- **No AutoML / Low-Code Modeling Tools:** No automated end-to-end modeling platforms, AutoML tools, or black-box low-code suites were used. The preprocessing pipelines, feature engineering, mathematical optimization formulations, and model architectures were designed and coded by the team.

---

## 2. AI-Assisted Work

AI coding assistants (Claude and Gemini accessed via developer IDE / pair-programming interfaces) were utilized as interactive productivity tools for the following specific tasks:

1. **Code Structuring and Boilerplate Generation:**
   - Drafting repetitive DataFrame manipulation patterns (Pandas merges, groupby aggregations, reshaping).
   - Drafting Matplotlib visualization boilerplate and consistent chart styling (`src/xora/plotting.py`).
   - Drafting utility helper functions for time parsing and formatting (`src/xora/timeutils.py`).

2. **Refactoring, Linting, and Syntax Checking:**
   - Cleaning up syntax, organizing module structures, and maintaining modular imports within `src/xora/`.
   - Adding type hints and docstring formatting across utility functions.
   - Checking PuLP syntax for decision variable declarations and constraint syntax in `src/xora/allocation.py`.

3. **Documentation Drafting, Formatting, and Final Audit:**
   - Drafting initial markdown summaries for documentation (`docs/data_preprocessing.md`, `docs/task2b_policy.md`, `README.md`).
   - Formatting markdown tables, summarizing metric tables, and structuring deliverables to match competition guidelines.
   - Cross-checking booklet submission requirements during the final review to ensure complete alignment with judging deliverables.

---

## 3. Human-Authored and Team-Directed Work

All core intellectual decisions, analytical reasoning, and algorithmic logic were formulated and directed by the human team:

1. **Problem Framing and Domain Logic:**
   - Interpreting Waypoint Group's retail logistics constraints: brand priorities (Fresh vs. Style vs. Tech), pre-dawn delivery windows (03:30–08:00 AM), regional depot distribution (Peliyagoda vs. Kandy), and vehicle access restrictions (`van_only`).

2. **Label Construction Formulation:**
   - Identifying the critical domain insight that vehicles arriving early wait outside closed gates and that gate waiting time must be excluded from handling duration (`service_start = max(arrival_time, window_open_time)`).
   - Defining the lateness threshold (`arrival_time > window_close_time`).
   - Defining weekly demand aggregation logic by requested order dates, ISO calendar weeks, and isolation of chilled demand to Fresh.

3. **Leakage Prevention & Feature Strategy:**
   - Enforcing the strict 4:00 PM cutoff boundary so models rely exclusively on information available when plans are drafted.
   - Selecting features: route position, forward buffer slack, dock handling baselines, and environmental disruption indices.

4. **Model Architecture and Validation Strategy:**
   - Designing the 1,000-run Monte Carlo route simulation approach to capture route-level cascading delay accumulation.
   - Formulating the dual daily demand forecasting approach (trend regression + calendar LightGBM) to handle moveable festival weeks (e.g., Vesak).
   - Setting up rolling-origin backtests across historical seasons.

5. **Task 2B Optimization Hierarchy & Business Policies:**
   - Defining the strict lexicographical priority sequence (repeat deferrals -> chilled volume -> outlet reach -> Fresh ambient -> total volume -> minimizing second pre-dawn trips -> route distance).
   - Defining shadow-pricing for elective deferrals and replaying allocations against store clocks.

---

## 4. Verification and Audit

All code, data transforms, and model outputs were thoroughly verified by the team:
- Every line of AI-assisted code was reviewed, tested, and audited against the raw dataset specifications.
- Optimization outputs were independently validated using the competition's `check_allocation.py` script.
- Model performance was evaluated using reproducible holdout splits with fixed random seeds.
