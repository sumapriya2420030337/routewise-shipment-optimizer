# Evaluation method and measured results

## Dataset snapshot

The checked-in CSVs were generated with seed `2026`.

| Measure | Observed |
|---|---:|
| Shipments | 30 |
| Candidate routes | 120 |
| Candidates per shipment | 4 |
| Shipments with at least one computed-feasible route | 20 |
| Shipments with no computed-feasible route | 10 |
| Computed-feasible route records | 36 |
| Stored feasibility/scenario-label mismatch warnings | 0 |

All records are synthetic. Shipment `scenario_class` describes whether its
candidate set contains any route satisfying the shipment's limits.
`routes.csv:is_feasible` is a generated audit field. The optimizer independently
recomputes eligibility and only then compares the stored label.

## Field definitions and units

### `shipments.csv`

| Field | Definition | Unit / valid values |
|---|---|---|
| `shipment_id` | Unique shipment key | Text |
| `origin`, `destination` | Synthetic endpoints | `City, CC` text |
| `cargo_type` | Synthetic cargo category | Text |
| `weight_kg` | Shipment mass | kg, positive |
| `distance_km` | Approximate lane distance | km, positive |
| `max_cost_usd` | Maximum route spend | USD, positive |
| `max_transit_days` | Maximum acceptable transit duration | days, positive |
| `max_delay_probability` | Maximum delay probability | unit interval `[0,1]` |
| `max_congestion_risk` | Maximum congestion risk | unit interval `[0,1]` |
| `max_geopolitical_risk` | Maximum geopolitical risk | unit interval `[0,1]` |
| `scenario_class` | Candidate-set feasibility audit label | `feasible` / `infeasible` |

### `routes.csv`

| Field | Definition | Unit / valid values |
|---|---|---|
| `route_id` | Unique candidate key | Text |
| `shipment_id` | Referenced shipment | Existing shipment ID |
| `route_mode` | Synthetic transport mode | `air`, `ocean`, `rail`, `road` |
| `cost_usd` | Estimated route cost | USD, positive |
| `transit_time_days` | Estimated duration | days, positive |
| `delay_probability` | Candidate delay probability | unit interval `[0,1]` |
| `congestion_risk` | Candidate congestion risk | unit interval `[0,1]` |
| `geopolitical_risk` | Candidate geopolitical risk | unit interval `[0,1]` |
| `is_feasible` | Stored audit label against all shipment limits | Boolean text `true` / `false` |

## Method

For each candidate, the engine checks cost, transit days, delay probability,
congestion risk, and geopolitical risk against the corresponding shipment
maximum. An option is feasible only when **all five** limits are met. A user may
override supported maxima for a request; missing or invalid numeric values are
rejected rather than silently defaulted. If no option meets the limits, the API
returns `no_feasible_route`, no recommendation, and candidate-specific rejection
reasons.

For each shipment, cost and transit time are min-max normalized across only its
computed-feasible alternatives:

```text
normalized(x) = (x - min(eligible x)) / (max(eligible x) - min(eligible x))
```

When all eligible routes have the same value for a metric, that metric maps to
`0.5` for every option. The risk penalty is not normalized:

```text
risk_penalty = 0.50 * delay_probability
             + 0.25 * congestion_risk
             + 0.25 * geopolitical_risk
```

The coefficients are illustrative, not fitted or calibrated. The objective is:

```text
total_penalty = w_cost * normalized_cost
              + w_time * normalized_transit_time
              + w_risk * risk_penalty
```

Lower penalties rank earlier. Weights must be finite and nonnegative and sum to
1 within absolute tolerance `1e-9`. Named profiles are
`cost_sensitive (0.60, 0.15, 0.25)`,
`balanced (0.40, 0.30, 0.30)`,
`time_sensitive (0.15, 0.60, 0.25)`, and
`reliability_sensitive (0.15, 0.15, 0.70)`, listed in cost/time/risk order.
The route ID deterministically breaks ties at the displayed six-decimal score.
Displayed weighted contributions use the same weights and are rounded so the
reported components reconcile with the displayed total.

The comparison strategies choose the minimum feasible cost, transit time, or
risk penalty (route ID breaks ties). Each choice is scored for comparison using
the balanced objective. Feasibility rate in the table means selected routes
divided by **all 30 shipments**, so it is expected to be 20/30 when ten
shipments have no eligible choice.

Pareto counts are computed separately per shipment over its feasible routes,
minimizing cost, time, and the illustrative risk penalty. One route dominates
another when it is no worse on all three measures and strictly better on at
least one.

## Results (balanced objective)

Reproduce with `backend\.venv\Scripts\python.exe scripts\evaluate_optimizer.py`.
Values below are produced from the checked-in CSVs at report generation time.

| Strategy | Selected | Feasibility rate | Constraint violations | Avg cost (USD) | Avg time (days) | Avg risk penalty | Avg balanced penalty |
|---|---:|---:|---:|---:|---:|---:|---:|
| Weighted optimizer | 20 | 66.67% | 0 | 17,111.63 | 19.25 | 0.397475 | 0.414555 |
| Cheapest feasible | 20 | 66.67% | 0 | 14,874.19 | 20.34 | 0.425638 | 0.420191 |
| Fastest feasible | 20 | 66.67% | 0 | 23,946.93 | 17.09 | 0.396181 | 0.449167 |
| Reliability-oriented | 20 | 66.67% | 0 | 19,831.00 | 18.71 | 0.379493 | 0.437946 |

All strategies selected only routes meeting recomputed constraints. There were
zero constraint violations and zero mismatches between stored labels and
computed feasibility in this generated snapshot. The weighted strategy's
average balanced penalty was `0.414555` versus `0.420191` for the cheapest
strategy. The cheapest choice had lower average spend (`$14,874.19`) but longer
average time (`20.34` days) and higher average risk penalty (`0.425638`) than
the weighted choice. The fastest option averaged `17.09` days and
`$23,946.93`; the reliability-oriented option averaged risk penalty `0.379493`
at average cost `$19,831.00`. These are descriptive outcomes, not savings
claims or evidence that a strategy is universally superior.

## Sensitivity and Pareto observations

Comparing each named profile's selected route with balanced on the 20 feasible
shipments, the cost-sensitive profile changes 2 selections, time-sensitive
changes 7, and reliability-sensitive changes 3. This shows that route choice
depends on the stated preferences for this dataset; it is not a prediction of
operational stability under real conditions.

## Hypothetical disruption simulation

`POST /api/v1/simulate-disruption` takes one shipment, the selected profile,
weights, optional supported constraint overrides, and 1–6 uniquely named scenarios. It first computes an unchanged
baseline, then makes fresh route-record copies for each scenario and calls the
same optimizer on those transformed records. Risk/probability increments are
additive and capped at 1.0. Cost and transit-time percentage increases apply
multiplicatively; per-scenario selectors can target route IDs and/or modes, and
the selectors intersect. No transformation writes to the original CSV files or
in-memory route records.

Each scenario returns the baseline and disrupted recommendation, feasibility
and rejection reasons per candidate, changed route metrics, ranks and scores,
feasible-candidate count/percentage, recommendation changes, and whether a
fallback route is available. When all routes become ineligible, the status is
`no_feasible_route`; there is no winner. The simulation parameters are
illustrative deterministic stress inputs, not probabilities of future events,
real-world forecasts, or measured operational resilience.

Run API and service tests with:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_disruption_simulator.py" -v
backend\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_api.py" -v
```

Across the 36 computed-feasible route records, 34 are non-dominated in their
respective shipment groups. The average per-shipment frontier size among the
20 feasible shipments is 1.7. No shipment has a selected route when all of its
candidates violate at least one hard constraint.

## Reproduction and limitations

```powershell
backend\.venv\Scripts\python.exe scripts\generate_dataset.py
backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
backend\.venv\Scripts\python.exe scripts\evaluate_optimizer.py
backend\.venv\Scripts\python.exe scripts\generate_technical_report.py
Set-Location frontend; npm test; npm run lint; npm run build
```

No real-world optimal route, predictive accuracy, or business savings can be
inferred from these generated values. The dataset is small, fixed-seed, and
synthetic; the risk blend and profiles are assumptions; the Pareto model omits
other operational objectives; and the engine does not model uncertainty,
capacity, carrier schedules, emissions, or live disruptions. Validate the
limits, costs, and risk coefficients with domain owners and governed real data
before using the method operationally.

## Optional AI Logistics Analyst

The Decision Lab's analyst is an optional commentary layer. The API recomputes
the optimization result from the shipment, candidate routes, active weights,
and constraints before constructing the analyst response. It includes
server-computed selected-route facts and feasible comparison facts; provider
text cannot change feasibility, ranking, or displayed authoritative values.
Groq JSON output is schema-validated and narratives containing unsupported
numeric claims are rejected. Missing keys, provider errors, or invalid output
produce deterministic local commentary. No live Groq request or model-quality
claim is included in the measured optimizer evaluation.

Set `GROQ_API_KEY` only in the backend process environment to enable live
commentary. `GROQ_PROVIDER` and `GROQ_MODEL` configure the provider/model. The
feature is user-triggered and sends a minimized set of computed shipment and
route facts to Groq; do not include sensitive shipment data in this synthetic
demo. The application and optimizer tests require no key.
