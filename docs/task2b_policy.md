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

## Unavoidable and elective deferrals

- **Unavoidable:** an order no available vehicle can carry. In S1 that is S1-078 (Style, OUT070, 40.7 m3), bigger than the largest truck (38 m3). The fix is commercial: ask the outlet to split the order.
- **Capacity-forced:** with four of seven reefer trucks in the workshop, no valid plan serves more than 132.8 m3 of the 181.6 m3 of chilled goods. About 49 m3 of chilled goods must wait; the optimiser proves this.
- **Elective:** which chilled orders wait is a choice. We choose the set that reaches the most stores. Each deferred order carries a price: what serving it instead would cost other stores. A store manager who pushes back gets that answer, not a refusal.

## Result for S1

76 of 85 orders (320 of 410 m3) ride on 24 trips. All ten repeat deferrals ride. All Fresh ambient and all Style and Tech orders that fit a truck ride. Chilled: 132.6 m3 to 18 of 26 stores. The plan passes Waypoint's allocation checker.

## Cost and impact trade-offs

- **Volume against stores.** Giving up 0.25 m3 of chilled volume reaches one more store. Each elective deferral is priced: most swaps cost under 1 m3, the Matara order about 9 m3, and serving a `van_only` Colombo store would cost 1.6 m3, more than the policy allows.
- **The planning standard against the clock.** The standard leaves out the drive back between trips and store opening times. Replayed on the clock, five chilled stops on second pre-dawn reefer trips reach stores after opening (eleven stops on a typical day of traffic). Those stores are warned the evening before, and drivers get clock times, not planning minutes.
- **Workshop repairs.** One large reefer truck back for the morning recovers about 35 m3 of chilled goods and five stores; the reefer van recovers about 10 m3 and is the only way to bring chilled goods to `van_only` outlets. On a peak day the workshop should release a large reefer truck first.
- **Tomorrow.** Every order deferred today becomes a priority 1 order tomorrow, so no store goes two days without its goods.
