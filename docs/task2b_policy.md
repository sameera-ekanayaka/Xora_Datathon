# Peak-day allocation policy

How Waypoint decides which orders ride and which wait when the fleet is short. Worked example: scenario S1, Peliyagoda, a peak day before a festival with ten vehicles in the workshop. Full workings are in `notebooks/07_task2b_peak_day_allocation.ipynb`.

## Rules we never break

One brand and one district per trip. Whole orders only. Chilled goods only on reefers, `van_only` outlets only by van, vehicles only from their own depot. Volume and weight within caps. At most two trips per vehicle, with planned minutes inside 270 for Fresh (03:30 to 08:00) and 480 for Style and Tech.

## Priorities, in this order

1. **No outlet waits two days in a row.** Orders deferred yesterday ride first.
2. **Chilled goods.** They spoil and only reefers can carry them. We may give up at most 1% of the best chilled volume if that gets chilled goods to more stores.
3. **Fresh ambient.** Fresh shelves must be stocked before 8 AM.
4. **Total volume.** Style and Tech can absorb a day's wait more easily than Fresh.
5. **Fewest second pre-dawn trips.** A truck that drives back and reloads rarely makes the 8 AM opening.
6. **Fewest kilometres** among plans that are equal on everything above.

Each priority is solved to its best value and locked before the next is considered, so a lower priority can never buy itself a better score at the expense of a higher one.

## Worked trip-time calculation

Per the booklet standard ($\text{trip minutes} = \text{outbound} + \text{inter-stop} + \text{handling}$), here is the calculation for **VEH006 Trip 1** (Fresh Colombo, 4 chilled orders: OUT008, OUT005, OUT009, OUT007):

| Component | Reference and calculation | Minutes |
|---|---|---|
| Depot to Colombo | `depot_to_district_freeflow_min` from `district_travel.csv` | 24 |
| Travel between 4 stops | `inter_stop_freeflow_min` = 8; $8 \times (4 - 1)$ | 24 |
| Handling stop 1 (OUT008) | Fresh + `rear_dock` from `service_allowance.csv` | 15 |
| Handling stop 2 (OUT005) | Fresh + `rear_dock` from `service_allowance.csv` | 15 |
| Handling stop 3 (OUT009) | Fresh + `rear_dock` from `service_allowance.csv` | 15 |
| Handling stop 4 (OUT007) | Fresh + `street` from `service_allowance.csv` | 16 |
| **Trip total** | $24 + 24 + 15 + 15 + 15 + 16$ | **109** |

**Daily budget check:** Combined with Trip 2 (Fresh Gampaha, 4 orders, 125 min), vehicle VEH006 uses $109 + 125 = \mathbf{234\text{ minutes}}$, fitting inside the 270-minute Fresh pre-dawn budget (03:30 to 08:00 AM) on 2 trips.

## Unavoidable and elective deferrals

Comparing the scenario files against `task2b_peak_day_fleet.csv` and `vehicles.csv`, Peliyagoda has **ten vehicles in the workshop** (5 ambient trucks, 4 reefer trucks, 1 reefer van; 28 available).
- **Unavoidable:** S1-078 (Style, OUT070, 40.7 m³) is bigger than the largest truck (38 m³). The commercial fix is to split the order.
- **Capacity-forced:** With **four of seven reefer trucks** in the workshop (plus one reefer van), over 55% of refrigerated capacity is offline. Only 4 reefers are available (86.2 m³ single-trip capacity). No valid plan can serve more than 132.8 m³ of the 181.6 m³ chilled demand; about 49 m³ must wait. The optimiser proves this.
- **Elective:** Which chilled orders wait is a choice. We serve 132.6 m³ to 18 stores instead of 132.8 m³ to 17 stores, giving up 0.2 m³ to reach an extra store. Each deferred order carries a price: what serving it instead would cost other stores (see Appendix B).

## Result for S1

76 of 85 orders (320 of 410 m³) ride on 24 trips. All ten repeat deferrals ride. All Fresh ambient and all Style and Tech orders that fit a truck ride. Chilled: 132.6 m³ to 18 of 26 stores. The plan passes Waypoint's allocation checker.

## Cost and impact trade-offs

- **Stores vs volume:** Sacrificing 0.25 m³ chilled volume reaches one more store.
- **Clock replay:** Accounting for depot reloads and store opening times, 5 chilled stops on second trips arrive after opening. Stores receive early warnings, and drivers receive clock schedules.
- **Workshop priority:** Releasing one large reefer truck recovers ~35 m³ and 5 stores; the reefer van recovers 10 m³ and unlocks van-only chilled stores.
- **Tomorrow:** Every deferred order becomes Priority 1 tomorrow, preventing consecutive misses.

---

# Appendix: Supporting Fleet Data and Deferral Pricing

### Appendix A: Fleet Availability Breakdown (Peliyagoda)

| Vehicle Category | Total at Depot | Available in S1 | In Workshop | Offline Share | Available Capacity / Trip |
|---|---|---|---|---|---|
| **Ambient Truck** | 27 | 22 | 5 | 18.5% | 656.0 m³ |
| **Ambient Van** | 2 | 2 | 0 | 0.0% | 17.0 m³ |
| **Reefer Truck** | 7 | 3 (VEH003, VEH006, VEH007) | 4 (VEH001, VEH002, VEH004, VEH005) | **57.1%** | 79.2 m³ |
| **Reefer Van** | 2 | 1 (VEH036) | 1 (VEH035) | 50.0% | 7.0 m³ |
| **Total** | **38** | **28** | **10** | **26.3%** | **759.2 m³** |

*Demand context:* Ambient demand is 228.2 m³ (easily served by 673 m³ ambient capacity). Chilled demand is 181.6 m³, exceeding the 86.2 m³ single-trip reefer capacity and bounded by the 270-minute pre-dawn limit to 132.8 m³ maximum throughput.

### Appendix B: Deferral Reasons and Shadow Prices

| Order Ref | Outlet | Brand | District | Temp | Volume (m³) | Days Since Served | Reason Code | Price If Forced Into Plan |
|---|---|---|---|---|---|---|---|---|
| **S1-078** | OUT070 | Style | Kurunegala | Ambient | 40.66 | 2 | `TOO_BIG_FOR_ANY_VEHICLE` | Exceeds max truck cap (38 m³) |
| **S1-021** | OUT013 | Fresh | Colombo | Chilled | 9.90 | 1 | `REEFER_CAPACITY` | Net loss: -0.19 m³ chilled volume |
| **S1-056** | OUT053 | Fresh | Galle | Chilled | 3.75 | 2 | `REEFER_CAPACITY` | Net loss: -0.54 m³ chilled volume |
| **S1-071** | OUT065 | Fresh | Kurunegala | Chilled | 12.04 | 1 | `REEFER_CAPACITY` | Net loss: -0.96 m³ chilled volume |
| **S1-073** | OUT066 | Fresh | Kurunegala | Chilled | 5.77 | 1 | `REEFER_CAPACITY` | Net loss: -0.96 m³ chilled volume |
| **S1-075** | OUT067 | Fresh | Kurunegala | Chilled | 7.24 | 2 | `REEFER_CAPACITY` | Net loss: -0.96 m³ chilled volume |
| **S1-003** | OUT002 | Fresh | Colombo | Chilled | 1.84 | 1 | `REEFER_CAPACITY` | Pushes out 1 store (-1.63 m³) |
| **S1-005** | OUT003 | Fresh | Colombo | Chilled | 1.72 | 2 | `REEFER_CAPACITY` | Pushes out 1 store (-1.63 m³) |
| **S1-064** | OUT060 | Fresh | Matara | Chilled | 6.78 | 1 | `REEFER_CAPACITY` | Net loss: -8.95 m³ chilled volume |
