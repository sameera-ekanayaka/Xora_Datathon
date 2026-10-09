# Peak-day allocation policy

How Waypoint decides which orders ride and which wait when the fleet is short. Worked example: scenario S1, Peliyagoda, a peak day before a festival with ten vehicles in the workshop. Full workings are in `notebooks/07_task2b_peak_day_allocation.ipynb`.

---

## 1. Rules we never break

Every valid allocation must satisfy all operating constraints:
1. **One brand and one district per trip.** All orders sharing a `(vehicle_id, trip_id)` must belong to the same brand and district.
2. **Refrigeration.** Orders with `temp_requirement = chilled` require `vehicle_temp = reefer`. Ambient orders may ride on reefers or ambient vehicles.
3. **Vehicle access.** Outlets with `parking_constraint = van_only` require `vehicle_type = van`.
4. **Home depot.** A vehicle may only serve outlets assigned to its home depot (Peliyagoda for S1).
5. **Whole orders.** Orders are never split across vehicles or trips.
6. **Capacity.** For each trip, total volume $\le$ `volume_cap_m3` and total weight $\le$ `weight_cap_kg`.
7. **Trips and time.** At most two trips per vehicle per day. Fresh trips must fit within the 270-minute pre-dawn budget (03:30 to 08:00 AM). Style and Tech trips must fit within the 480-minute trading day budget.

---

## 2. Fleet Availability and Workshop Analysis

Comparing the scenario files against `task2b_peak_day_fleet.csv` and `vehicles.csv` reveals why the fleet is constrained on day S1:

### Fleet Status Breakdown (Peliyagoda Depot)

| Vehicle Category | Total in Fleet | Available in S1 | In Workshop | Offline Share | Available Capacity / Trip | Offline Capacity / Trip |
|---|---|---|---|---|---|---|
| **Ambient Truck** | 27 | 22 | **5** | 18.5% | 656.0 m³ | 132.0 m³ |
| **Ambient Van** | 2 | 2 | **0** | 0.0% | 17.0 m³ | 0.0 m³ |
| **Reefer Truck** | 7 | **3** (VEH003, VEH006, VEH007) | **4** (VEH001, VEH002, VEH004, VEH005) | **57.1%** | 79.2 m³ | **114.3 m³** |
| **Reefer Van** | 2 | **1** (VEH036) | **1** (VEH035) | **50.0%** | 7.0 m³ | **7.0 m³** |
| **Total Peliyagoda Fleet** | **38** | **28** | **10 in workshop** | **26.3%** | **759.2 m³** | **253.3 m³** |

### Capacity Arithmetic: Why Chilled Goods are the Bottleneck
- **Plentiful Ambient Fleet:** 24 available ambient vehicles (22 trucks + 2 vans) provide 673 m³ of capacity per trip against total ambient demand of only 228.2 m³ (Fresh ambient 133.0 m³, Style 77.2 m³, Tech 18.1 m³). Ambient capacity is abundant.
- **Critical Reefer Shortage:** **Four of seven reefer trucks** (VEH001, VEH002, VEH004, VEH005) and **one of two reefer vans** (VEH035) are in the workshop. This removes **5 of Peliyagoda's 9 refrigerated vehicles (55.6% reefer outage)**, taking 121.3 m³ of refrigerated capacity offline.
- **The Chilled Gap:** Chilled demand is **181.6 m³** across 26 orders. The 4 remaining reefers (3 trucks + 1 van) have a combined single-trip capacity of **86.2 m³** (79.2 m³ + 7.0 m³). Even if every reefer ran two full trips, the maximum theoretical capacity is $2 \times 86.2 = 172.4\text{ m³} < 181.6\text{ m³}$.
- **Geographic Feasibility Limit:** In practice, long routes (Galle 118 min, Matara 152 min, Puttalam 188 min) prevent reefers from running two full distant trips within the 270-minute pre-dawn limit. The mathematical solver proves that **no feasible plan can deliver more than 132.8 m³** of chilled goods.

---

## 3. Trip Time Calculations: Worked Example

Per the challenge booklet, planned trip time is calculated in three steps:
$$\text{trip\_minutes} = \text{outbound travel} + \text{inter-stop travel} + \text{total handling time}$$

Here is the exact calculation for **VEH006, Trip 1** from our approved S1 allocation (carrying 4 Fresh chilled orders to Colombo: S1-014, S1-009, S1-016, and S1-012):

### Worked Trip-Time Calculation: VEH006 Trip 1 (Fresh Colombo, 4 orders)

| Component | Reference and calculation | Minutes |
|---|---|---|
| **Depot to Colombo** | `depot_to_district_freeflow_min` from `district_travel.csv` | **24** |
| **Travel between 4 stops** | `inter_stop_freeflow_min` = 8; $8 \times (4 - 1)$ | **24** |
| **Handle stop 1 (OUT008)** | Fresh + `rear_dock` from `service_allowance.csv` | **15** |
| **Handle stop 2 (OUT005)** | Fresh + `rear_dock` from `service_allowance.csv` | **15** |
| **Handle stop 3 (OUT009)** | Fresh + `rear_dock` from `service_allowance.csv` | **15** |
| **Handle stop 4 (OUT007)** | Fresh + `street` from `service_allowance.csv` | **16** |
| **Trip 1 Total** | $24 + 24 + 15 + 15 + 15 + 16$ | **109** |

### Vehicle Daily Budget Check
- **Trip 1 (Fresh Colombo):** 4 chilled orders, 32.8 m³ (98% volume fill), planned time = **109 minutes**.
- **Trip 2 (Fresh Gampaha):** 4 chilled orders, 26.2 m³ (79% volume fill), planned time = **125 minutes** ($37 + 9 \times 3 + 15 \times 3 + 16 = 125$).
- **Combined Vehicle Time:** $109 + 125 = \mathbf{234\text{ minutes}} \le \mathbf{270\text{ minutes}}$ (Fresh pre-dawn budget, 03:30 to 08:00 AM).
- **Trips per Vehicle:** Exactly 2 trips (within the 2 trips/day limit).

---

## 4. Priorities, in this order

1. **No outlet waits two days in a row.** Orders deferred yesterday ride first.
2. **Chilled goods.** They spoil and only reefers can carry them. We may give up at most 1% of the best chilled volume if that gets chilled goods to more stores.
3. **Fresh ambient.** Fresh shelves must be stocked before 8 AM.
4. **Total volume.** Style and Tech can absorb a day's wait more easily than Fresh.
5. **Fewest second pre-dawn trips.** A truck that drives back and reloads rarely makes the 8 AM opening.
6. **Fewest kilometres** among plans that are equal on everything above.

Each priority is solved to its best value and locked before the next is considered, so a lower priority can never buy itself a better score at the expense of a higher one.

---

## 5. Unavoidable and Elective Deferrals

- **Unavoidable:** An order no available vehicle can physically carry. In S1 that is **S1-078** (Style, OUT070, Kurunegala, 40.66 m³), which exceeds the largest truck's capacity (38.0 m³). Commercial remedy: outlet must split large bulk orders.
- **Capacity-Forced:** With 4 of 7 reefer trucks in the workshop, chilled capacity is capped at 132.8 m³. Exactly ~49 m³ of chilled goods must wait; this is mathematically proven.
- **Elective (Prioritized Selection):** Which chilled orders wait is an explicit policy choice. We chose to deliver 132.6 m³ across 18 stores rather than 132.8 m³ across 17 stores (giving up 0.2 m³ to serve an additional outlet). Every elective deferral is shadow-priced by what serving it would cost other stores.

| Order Ref | Outlet | Brand | District | Temp | Volume (m³) | Days Since Served | Reason Code | Impact If Served Instead |
|---|---|---|---|---|---|---|---|---|
| **S1-078** | OUT070 | Style | Kurunegala | Ambient | 40.66 | 2 | `TOO_BIG_FOR_ANY_VEHICLE` | Physically impossible on single truck |
| **S1-021** | OUT013 | Fresh | Colombo | Chilled | 9.90 | 1 | `REEFER_CAPACITY` | Net loss: -0.19 m³ chilled volume |
| **S1-056** | OUT053 | Fresh | Galle | Chilled | 3.75 | 2 | `REEFER_CAPACITY` | Net loss: -0.54 m³ chilled volume |
| **S1-071** | OUT065 | Fresh | Kurunegala | Chilled | 12.04 | 1 | `REEFER_CAPACITY` | Net loss: -0.96 m³ chilled volume |
| **S1-073** | OUT066 | Fresh | Kurunegala | Chilled | 5.77 | 1 | `REEFER_CAPACITY` | Net loss: -0.96 m³ chilled volume |
| **S1-075** | OUT067 | Fresh | Kurunegala | Chilled | 7.24 | 2 | `REEFER_CAPACITY` | Net loss: -0.96 m³ chilled volume |
| **S1-003** | OUT002 | Fresh | Colombo | Chilled | 1.84 | 1 | `REEFER_CAPACITY` | Pushes out 1 store (-1.63 m³) |
| **S1-005** | OUT003 | Fresh | Colombo | Chilled | 1.72 | 2 | `REEFER_CAPACITY` | Pushes out 1 store (-1.63 m³) |
| **S1-064** | OUT060 | Fresh | Matara | Chilled | 6.78 | 1 | `REEFER_CAPACITY` | Net loss: -8.95 m³ chilled volume |

---

## 6. Result for S1

- **76 of 85 orders** (320.2 of 409.9 m³, 78.1% of total volume) ride on 24 trips across 17 vehicles (4,218 total km).
- **100% of repeat deferrals** ride (all 10 orders deferred yesterday are served today).
- **100% of Fresh ambient, Style, and Tech orders** that physically fit a vehicle are served.
- **Chilled goods:** 132.6 m³ delivered to 18 of 26 stores (within 0.2% of proven mathematical maximum).
- **Full Validation:** 100% compliant with Waypoint's `check_allocation.py`.

---

## 7. Cost and Impact Trade-offs

- **Volume against Stores:** Giving up 0.25 m³ of chilled volume reaches one more store.
- **The Planning Standard against the Clock:** Replayed on the clock accounting for depot reload times and store opening hours, 5 chilled stops on second pre-dawn trips arrive after store opening. Store managers receive pre-dawn arrival alerts and drivers get clock schedules rather than generic duration allowances.
- **Workshop Repair Ranking:** If the workshop can expedite repairs, releasing one large reefer truck (VEH004 or VEH005) recovers 35.3 m³ of chilled volume and 5 unserved stores. Releasing the reefer van (VEH035) recovers 7.0 m³ and unlocks van-only chilled deliveries.
- **Next-Day Guarantee:** Every order deferred today is flagged as `deferred_yesterday = 1` tomorrow, giving it Priority 1 status so no store suffers consecutive deferrals.
