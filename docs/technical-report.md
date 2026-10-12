# RouteWise — technical report

**Explainable Shipment Route Optimizer**  
Assignment prototype · measured against the included synthetic dataset

## Problem and scope

Selecting a shipment route is a constrained multi-objective choice: cost,
delivery time, and multiple sources of risk may conflict. RouteWise demonstrates
a reproducible, explainable way to compare geographically supported candidate
modes per shipment.
It is a local decision-support prototype, not a carrier recommendation or a
forecasting service. No machine-learning model is trained.

The fixed-seed dataset contains 30 shipments and 68 route candidates (one to
four per shipment, depending on geography). Twenty shipments have at least one
candidate meeting their limits; ten have none. Twenty-four route records are
computed feasible. The records, lane values, and risk metrics are synthetic.

## Methodology

The backend first validates shipment and route records and recomputes each
candidate's eligibility. A candidate is eligible only when its USD cost, days
in transit, delay probability, congestion risk, and geopolitical risk all meet
the shipment's corresponding hard maximum. CSV labels are audit targets. If no
candidate qualifies, the result is explicitly `no_feasible_route`, with no
winner and reasons for every rejection.

For eligible candidates, cost and transit time are independently min-max
normalized within that shipment's eligible set. A constant-valued metric maps
to `0.5`. The illustrative risk score is
`0.50*delay + 0.25*congestion + 0.25*geopolitical risk`. The weighted objective
is `w_cost*normalized_cost + w_time*normalized_time + w_risk*risk_penalty`.
Weights are nonnegative and sum to one within `1e-9`. The default balanced
weights are 0.40/0.30/0.30; additional cost-, time-, and reliability-oriented
profiles are supported. The lower score ranks first, with route ID as the
deterministic tie-breaker. The API exposes normalized scores, weighted
contributions, active constraints/weights, explanations, and rejection
reasons.

## Architecture

The React/TypeScript dashboard calls a typed FastAPI service. Pydantic schemas
validate requests and responses. `route_optimizer.py` is the sole authority
for feasibility and scoring; `evaluation.py` reuses the engine for weighted
selections and profile comparisons and evaluates cheapest, fastest, and
reliability-oriented feasible baselines. CSV loading is relative to the
project, and the optimizer can be called as a Python service without the web
server. There is no database or model-training process. An optional,
user-triggered AI Logistics Analyst can request structured Groq commentary over
server-recomputed optimizer facts. It cannot alter route selection, feasibility,
or scores; missing credentials and provider/validation failures use deterministic
local commentary. No live provider-quality claim is included in the evaluation.

## Measured evaluation

The balanced run selects a route for 20 of 30 shipments (66.67%); the other ten
are correctly left without a recommendation. All four selection strategies
have zero constraint violations. There are zero stored-label/computed
feasibility mismatches.

| Strategy | Avg cost (USD) | Avg time (days) | Avg risk penalty | Avg balanced penalty |
|---|---:|---:|---:|---:|
| Weighted optimizer | 32,393.19 | 16.73 | 0.382401 | 0.439720 |
| Cheapest feasible | 32,393.19 | 16.73 | 0.382401 | 0.439720 |
| Fastest feasible | 33,043.46 | 16.05 | 0.373758 | 0.452127 |
| Reliability-oriented | 33,371.38 | 16.28 | 0.368315 | 0.480494 |

The weighted and cheapest strategies select the same route records in this
dataset; that is an observed outcome, not a forced or hard-coded result. The
fastest and reliability-oriented strategies expose different time, cost, and
risk trade-offs. These outcomes are descriptive and do not represent
ground-truth optimality or realized savings.

Across the 20 feasible shipments, profile choices differ from balanced for 0
cost-sensitive, 3 time-sensitive, and 2 reliability-sensitive choices.
Per-shipment Pareto analysis found 24 non-dominated candidates out of 24
computed-feasible candidates, averaging 1.2 frontier routes per feasible
shipment.

## Hypothetical disruption simulation

The Disruption Lab applies deterministic, user-specified risk increments and
percentage cost/time changes to copies of selected route records. The API
recomputes feasibility and reranks each transformed candidate set through the
same optimizer. Responses compare baseline and disrupted candidate metrics,
constraint rejections, feasible counts, recommendation changes, and fallback
availability. If every candidate violates its active limits, no recommendation
is returned. The original dataset is not mutated. This scenario analysis is a
synthetic stress-testing capability, not a forecast or evidence of actual
network resilience.

The dashboard also offers browser-persisted appearance/density preferences,
approximate currency display, accessible keyboard navigation, route comparison,
CSV downloads, and session-only recent activity. Currency conversion affects
presentation only; the scored data remains in USD.

The analyst requires no API key for core app operation. When enabled, its
minimized request context includes the selected candidate's computed metrics,
active weights and constraints, feasible comparison candidates, and rejection
reasons. Groq output is schema-validated and not used as a source of numeric
facts. Keep credentials in the backend environment and use only non-sensitive
data with the optional provider.

## Limitations and next steps

The dataset is small and synthetic. Risk coefficients, constraints, and
profiles are illustrative and not calibrated. This evaluation does not
establish accuracy, operational robustness, or financial benefit; it omits
capacity, schedules, emissions, uncertain inputs, and live events. A production
decision tool would need domain-reviewed limits, validated real data, freshness
and lineage controls, operational monitoring, and explicit human review.
Potential follow-on analysis includes stakeholder-approved weight sensitivity,
broader Pareto objectives, and testing under observed disruption scenarios.

To regenerate the data, execute the test suite, measure the strategies, and
rebuild the PDF, run the four commands listed in the root README.
