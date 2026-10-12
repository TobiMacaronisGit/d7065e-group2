# Occupancy forecast: result, explanation, and the timetable idea

Notes from 10 Oct 2026, for report §11 (evaluation) and §13 (risks / reflection / future work).

## 1. Result: the trained model loses to persistence

`make train` (lr-v1, split by simulated date, 18 training days 2026-10-02..19, test day 2026-10-20,
23,755 train / 1,105 test samples). Raw output: `docs/results/train.txt`.

| Horizon | MAE model (people) | MAE persistence (people) |
|---|---|---|
| 5 min  | 2.17 | **1.29** |
| 10 min | 3.97 | **2.36** |
| 15 min | 5.48 | **3.19** |
| 20 min | 6.90 | **3.99** |
| 25 min | 8.09 | **4.65** |
| 30 min | 9.21 | **5.34** |

The linear model (lags 0–60 min + time of day, least squares per horizon) is ~1.7x worse at every
horizon. Our own rule (`planner/forecast.py`): persistence is "the baseline every evaluation must beat".
So the model is **not deployed**; it is kept as `docs/results/model-lr-v1.json` for reference only.
`planner/model.json` must not exist, otherwise `make up --build` bakes it into the planner image.

Caveat: one test day only. Comparing several model variants on this same day would be tuning on the
test set, so we deliberately did not.

## 2. Why persistence wins (backed by the occupancysim source)

From the course repo, `occupancysim/internal/sim/plan.go` and `occupancysim/docs/model.md`:

- A whole day is generated at midnight from `seed` + date. Randomness is only in this generation:
  which lecture rooms are booked per slot, how many lectures each student takes (1–3), which slots.
- Lecture rooms are drawn **in random order for every slot and every day**, so "A109 at 08:15" does not
  repeat from day to day.
- Within a day occupancy is a step function: empty → ~students+lecturer at once → empty.

Consequence: per-room history + time of day carries almost no information about *when* the next lecture
in *this* room starts. Persistence is exactly right during every constant phase and only wrong at the
jumps; the least-squares model hedges ("maybe a few people") at every step, which accumulates under MAE.

## 3. The timetable idea (future work, not implemented)

occupancysim publishes the day's bookings: `GET /api/state` → `lectures[]` with `room`, `start`, `end`,
`students`, `seats`. Once the day is generated:

- every student signed up for a lecture attends (no no-shows),
- students arrive exactly 10 min before start, the lecturer 15 min before,
- lectures nobody signed up for are dropped in advance.

So a planner reading the timetable would get a near-perfect forecast; the only deviation is walking time
from the entrance (a few minutes of ramp-up). That is **not realistic**: a real booking system knows
who registered, not who shows up. Using it here would look like reading the answer key.

What a realistic version would need: a no-show / late-arrival model applied to the bookings. The
simulator does not provide one, so the result would mainly reflect noise parameters we picked ourselves —
hard to defend, and not worth it before the deadline.

Suggested report sentence: *"The right input for the forecast is the booking system, not a better
model. occupancysim exposes bookings with exact attendance; a credible evaluation would require a
no-show model, which the simulator does not provide. We therefore kept persistence and list a
timetable-based forecast with a no-show model as future work."*

## 4. Decision (p2-5) — taken 10 Oct after the live E3 runs

**The planner stays, with the timetable forecast** (rooms without bookings fall back to persistence).
Live result for the lecture rooms: reactive only 149 sim-min over 1000 ppm, persistence 20, timetable 0,
at +14 % / +16 % heating energy. Details: [`results/e3-summary.md`](results/e3-summary.md).
Section 3's "future work" became the implementation (`planner/forecast.py: timetable_forecast`), using
*registered* students — the missing no-show model remains a stated limitation.

### Options considered before the decision

- **Keep the planner with persistence forecast + CO₂ rollout** (what is running now). Story: trained,
  evaluated on a held-out day, lost to the baseline, so persistence is used; the planner still rolls the
  CO₂ physics forward 30 min. Both of us must be able to explain this at the exam.
- **Drop the planner**: less to explain, but the measured result above is lost.
