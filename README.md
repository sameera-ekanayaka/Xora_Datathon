# Xora delivery analytics

Xora's data science work on delivery planning for Waypoint Group.

Waypoint Group runs 60 vehicles from two depots to 120 outlets across three retail brands. This repo answers three questions for them:

| Task | Question | Output |
|---|---|---|
| Task 1 | How long will each delivery take at the outlet, and how likely is the truck to arrive after the window closes? | `submissions/submission_task1.csv` |
| Task 2A | How much volume (total and chilled) will each depot and brand need over the next 10 weeks? | `submissions/submission_task2a.csv` |
| Task 2B | On a peak day with vehicles in the workshop, which orders do we serve, on which truck, and which do we defer? | `submissions/submission_task2b.csv` and a written policy |

## How to run

```bash
git clone https://github.com/sameera-ekanayaka/xora_datathon.git
cd xora_datathon
python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .                   # makes the shared helpers in src/xora importable
```

Then unzip the data into `data/raw/` (see `data/README.md`) and run the notebooks in order.

## Notebook guide

Each notebook does one job and saves its results for the next one, so you can read them in order like chapters.

| # | Notebook | What it does |
|---|---|---|
| 01 | `notebooks/01_data_understanding.ipynb` | Profiles every file and shows what the data says about lateness, demand and the peak day |
| 02 | `notebooks/02_data_quality_and_cleaning.ipynb` | Checks every table against its expected rules, fixes what needs fixing and saves clean tables |
| 03 | `notebooks/03_label_construction.ipynb` | Builds the service-time and late labels for Task 1 and the weekly demand table for Task 2A |
| 04 | `notebooks/04_feature_engineering.ipynb` | Builds the Task 1 features from what a planner knows at the 4 PM cutoff, proves none of them leak, and audits each one |
| 05 | `notebooks/05_task1_service_and_lateness.ipynb` | Predicts service time and late risk by simulating each drafted route, compares it with a direct classifier, and writes the Task 1 predictions |
| 06 | `notebooks/06_task2a_demand_forecast.ipynb` | Forecasts daily demand and adds it up into ISO weeks so festival shifts are handled, with backtests and P10 to P90 ranges |
| 07 | `notebooks/07_task2b_peak_day_allocation.ipynb` | Plans the peak day with an optimiser that follows Waypoint's rules and a fixed order of priorities, prices every deferral, replays the plan on the clock and ranks workshop repairs |
| 08 | `notebooks/08_decision_layer.ipynb` | Turns the model outputs into plain instructions: a dispatcher risk board, driver run sheets, store messages, peak-day loading sheets and deferral notices, and a weekly reefer outlook |
| | `Xora_FinalNotebook.ipynb` | The full pipeline in one place, ending with model inference |

## Repo layout

```
check_allocation.py   Task 2B allocation checker, unchanged
data/                 local only: raw data and processed tables
notebooks/            one notebook per stage, numbered in reading order
src/xora/             small shared helpers (paths, loading, time parsing, data checks)
models/               saved model files
submissions/          the three submission CSVs
docs/                 diagrams, preprocessing document, Task 2B policy, model cards
reports/              figures and the experiment log
```

## Working practice

- `main` always runs. Work happens on a branch per stage and comes in through a pull request.
- Seeds are fixed and dependencies are pinned, so results reproduce.
