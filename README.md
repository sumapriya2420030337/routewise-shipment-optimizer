# RouteWise — Explainable Shipment Route Optimizer

RouteWise is a local full-stack logistics analytics demonstration. It compares
up to four geographically supported synthetic candidate routes per shipment,
enforces hard cost, delivery-time, and risk limits, and explains the selected
route using a deterministic weighted objective. The application includes a
FastAPI backend, a React/TypeScript dashboard, sensitivity analysis, a measured
baseline evaluation, and a hypothetical disruption simulator.
An optional AI Logistics Analyst can provide natural-language commentary on
optimizer-computed facts; the core application remains fully functional without
an AI provider or API key.

> **Data notice:** The included dataset is synthetic. Risk coefficients,
> profile weights, and scores are illustrative assumptions; they are not
> predictions, calibrated risk estimates, or evidence of real-world savings.

## Features

- Fixed-seed generator for 30 shipments and geographically supported candidates
  (one to four per shipment; 68 in the checked-in snapshot).
- Independent feasibility checks for budget, deadline, delay, congestion, and
  geopolitical-risk caps. Stored CSV labels are audited, not trusted.
- Four decision profiles and validated custom cost/time/risk weights.
- Route-level score breakdowns, deterministic rankings, rejection reasons, and
  explicit handling when a shipment has no eligible option.
- API-backed shipment explorer, route comparison, decision lab, measured
  strategy evaluation, weight-sensitivity view, and Disruption Lab.
- Validated Create Shipment workflow with deterministic illustrative candidate
  routes, optimizer-backed eligibility/ranking/explanations, and immediate
  re-optimization when decision settings change. New records are request-only
  and do not modify the CSV dataset or survive a page refresh.
- Browser-persisted theme, density, currency-display, reduced-motion, and
  sidebar preferences; keyboard command palette; sortable/filterable shipment
  list; route details and side-by-side comparison; session activity and CSV
  exports.
- Deterministic disruption scenarios re-optimize copied candidate records,
  report feasibility changes and fallback recommendations, and never mutate
  the source dataset.
- Cheapest, fastest, reliability-oriented, and weighted strategy comparisons,
  plus per-shipment Pareto-frontier counts.
- FastAPI OpenAPI docs and a reproducible three-page PDF technical report.
- Optional, manually triggered Groq commentary over server-computed results,
  with schema validation and a deterministic fallback when unavailable.
- Scroll-aware sidebar navigation that tracks the visible section, with
  fixed sidebar positioning and expanded/compact layouts.

## Project structure

```text
backend/app/main.py                 FastAPI endpoints and dataset loading
backend/app/schemas.py              Pydantic request/response contracts
backend/app/services/               Optimizer, evaluation, and simulation logic
data/shipments.csv                  Synthetic shipment constraints and metadata
data/routes.csv                     Four candidate routes per shipment
docs/                               Architecture, evaluation, technical report
frontend/src/                       React UI, typed API client, and UI tests
scripts/generate_dataset.py         Fixed-seed dataset generator
scripts/evaluate_optimizer.py       Evaluation CLI
scripts/generate_technical_report.py Rebuild the measured PDF report
tests/                              Dataset, optimizer, evaluation, and API tests
```

## Setup (Windows PowerShell)

Use two terminals from the repository root. Python 3.11+ and Node.js 20.19+ or
22.12+ are recommended (the project was also verified with Python 3.14 and
Node.js 24).

### Backend

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

The API reads `data\shipments.csv` and `data\routes.csv` relative to the
repository, regardless of the terminal's current directory. Optional local
configuration is documented in [backend/.env.example](backend/.env.example):
`ROUTEWISE_DATA_DIR` can point to another dataset directory, and
`ROUTEWISE_CORS_ORIGINS` configures allowed browser origins. The backend does
not automatically load `.env`; set these variables in the shell before
starting Uvicorn. Groq commentary is optional. To enable it, set
`GROQ_API_KEY` in the backend terminal; `GROQ_PROVIDER` and `GROQ_MODEL` are
configurable and default to `groq` and `openai/gpt-oss-20b`. Never commit a real
key. Without a key, the analyst returns deterministic local commentary and
optimization continues normally.

```powershell
$env:GROQ_API_KEY = "your-key"
$env:GROQ_PROVIDER = "groq"
$env:GROQ_MODEL = "openai/gpt-oss-20b"
backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to
`http://127.0.0.1:8000` during local development. To use a different API origin,
copy [frontend/.env.example](frontend/.env.example) to `frontend/.env.local` and
set `VITE_API_BASE_URL`; when it is blank, `ROUTEWISE_API_PROXY_TARGET` can
override the Vite proxy target (default `http://127.0.0.1:8000`). The browser
checks `GET /api/v1/health` on startup and when Retry is selected. If the API is
unavailable, start the backend command above in a separate terminal and retry.
A production static build is created by `npm run build` inside `frontend\`.

Displayed prices can be switched between USD, EUR (approx.), GBP (approx.),
and INR (approx.) in Display settings. USD remains the canonical currency for
the dataset, optimizer, constraints, API payloads, and raw exports. EUR (0.92
USD), GBP (0.79 USD), and INR (83.5 INR per USD) are fixed approximate
display-only conversions; they do not change optimization results.

Convenience PowerShell scripts are provided:

```powershell
.\scripts\start_backend.ps1
.\scripts\start_frontend.ps1
.\scripts\test_all.ps1
```

Install dependencies first. `test_all.ps1` runs the Python suite, frontend
tests, ESLint, and the TypeScript-checked production build.

## Dataset generation and validation

```powershell
backend\.venv\Scripts\python.exe scripts\generate_dataset.py
backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The generator uses seed `2026` by default, producing 30 shipment records and
68 geographically supported candidate route records in the checked-in snapshot.
It emits one to four candidates per shipment rather than inventing unavailable
transport modes. The current data contains 20 shipments with at least one
feasible route, 10 without any feasible option, and 24 computed-feasible route
records. Re-running the generator with the default seed reproduces the CSV
contents; `--seed` and `--output-dir` allow explicit alternatives.

The shipment and route columns, definitions, and units are described in
[docs/evaluation.md](docs/evaluation.md). Validation checks IDs, foreign keys,
numeric ranges, route counts, scenario classes, and computed feasibility labels.

## API

Interactive API documentation is available at
<http://127.0.0.1:8000/docs>; the OpenAPI schema is at
<http://127.0.0.1:8000/openapi.json>.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | API and loaded dataset status |
| GET | `/api/v1/metadata` | Dataset counts and measured evaluation |
| GET | `/api/v1/shipments` | Search/filter/page shipments |
| GET | `/api/v1/shipments/{shipment_id}` | Shipment detail and computed status |
| GET | `/api/v1/shipments/{shipment_id}/routes` | Feasible and rejected candidates |
| POST | `/api/v1/shipments/optimize-new` | Create a transient shipment and optimize synthetic or supplied candidates |
| POST | `/api/v1/optimize` | Optimize one shipment |
| POST | `/api/v1/sensitivity` | Compare recommendations across weight sets |
| POST | `/api/v1/simulate-disruption` | Re-optimize across bounded hypothetical disruption scenarios |
| POST | `/api/v1/analyst/explanation` | Explain server-computed results; uses deterministic commentary without Groq |

Example request:

```powershell
$body = @{
  shipment_id = "S001"
  profile = "balanced"
  constraint_overrides = @{ max_cost_usd = 30000 }
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/optimize `
  -ContentType "application/json" -Body $body
```

Unknown shipments return HTTP 404; malformed or invalid weights/overrides return
HTTP 422. A valid shipment with no route meeting its hard limits returns HTTP
200 with `status: "no_feasible_route"`, a null recommendation, and rejection
reasons for each candidate.

`POST /api/v1/shipments/optimize-new` accepts shipment constraints without a
pre-existing shipment ID. By default, it generates four reproducible candidate
routes and reports their metrics as **synthetic estimates**, not carrier
quotes, actual distances, or forecasts. Clients may instead submit 1–12
candidate routes. The result includes every candidate, independently computed
eligibility, score components, explanations, and rejection reasons. Its
`persistence: "request_only"` field reflects the actual lifecycle: the API
does not save these records, and the browser only keeps them in current-page
memory. Refreshing the page (or restarting the backend) loses them. Neither
CSV file is modified. Further optimizations use this same endpoint and the
existing Python optimizer; the frontend does not score routes.

Example request:

```powershell
$body = @{
  origin = "Hamburg, DE"
  destination = "Sao Paulo, BR"
  cargo_type = "electronics"
  weight_kg = 1200
  max_cost_usd = 25000
  max_transit_days = 30
  max_delay_probability = 0.8
  max_congestion_risk = 0.8
  max_geopolitical_risk = 0.8
  profile = "balanced"
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/shipments/optimize-new `
  -ContentType "application/json" -Body $body
```

The disruption endpoint accepts the same supported constraint overrides as
optimization plus 1–6 uniquely named scenarios. Additive risk
increments are capped at `1.0`; cost and transit increases are multiplicative
percentages from 0 to 500%. Scenarios can target up to four route IDs and/or
route modes (both selectors intersect). The response includes baseline and
disrupted rankings, per-candidate metric changes, rejection reasons, feasibility
counts, recommendation changes, and fallback availability. These are
hypothetical deterministic stress tests, not forecasts.

## Optimization and evaluation

The engine recomputes route feasibility for all shipment limits before ranking.
For the balanced profile, feasible routes are scored by:

```text
risk_penalty = 0.50 * delay_probability
             + 0.25 * congestion_risk
             + 0.25 * geopolitical_risk

total_penalty = cost_weight * normalized_cost
              + time_weight * normalized_transit_time
              + risk_weight * risk_penalty
```

Cost and transit time use min-max normalization among the feasible alternatives
for that shipment; identical values map to neutral `0.5`. Named profiles are
cost-sensitive, balanced, time-sensitive, and reliability-sensitive. Custom
weights must be finite, nonnegative, and sum to 1 within `1e-9`. Lower penalties
rank higher; route ID deterministically breaks exact displayed-score ties.
Additional assumptions, tie-breaking, invalid-value behavior, and evaluation
limitations are documented in [docs/evaluation.md](docs/evaluation.md).

Reproduce measured comparisons and generate a verified PDF report with:

```powershell
backend\.venv\Scripts\python.exe scripts\evaluate_optimizer.py
backend\.venv\Scripts\python.exe scripts\generate_technical_report.py
```

See [docs/evaluation.md](docs/evaluation.md) for the measured results and
[docs/technical-report.pdf](docs/technical-report.pdf) for the report. The PDF
is manually prepared and is not regenerated by project scripts.
These descriptive synthetic-data comparisons do not establish a ground-truth
optimal route, predictive accuracy, or business savings.

The UI's EUR/GBP/INR display uses fixed approximate conversion rates for
presentation only; optimizer inputs and exports retain USD values. User
preferences persist in browser storage; recent activity and newly created
shipments are current-page session state only.

## Tests and checks

From the repository root:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
Set-Location frontend
npm test
npm run lint
npm run build
```

The Python suite covers data integrity, feasibility recomputation, weights,
scoring, rankings, explanations, evaluation, and HTTP API contracts. Frontend
tests exercise dashboard data/recommendation display and profile/no-feasible
behavior, persisted settings, command-palette navigation, and scenario targeting
through the disruption API. The production build includes TypeScript project
compilation.

## Architecture and report

- [Architecture](docs/architecture.md)
- [Evaluation method and actual results](docs/evaluation.md)
- [Technical report (Markdown)](docs/technical-report.md)
- [Technical report (PDF)](docs/technical-report.pdf)

For a demo screenshot, run both services, open the local frontend, select a
shipment, and trigger optimization. Save the screenshot as a PNG in
`docs/screenshots/`; do not present synthetic results as production data.

## Limitations and future work

This is a local assignment prototype. The fixed dataset is small and generated;
the risk formula and weights are illustrative, and no calibrated forecasts,
external carrier feeds, persistence, authentication, or production deployment
are included. Pareto analysis is per shipment over cost, duration, and
illustrative risk. Future work should validate constraints and risk weights
with logistics stakeholders and real, appropriately governed data before any
operational use. The optional analyst sends minimized computed route facts to
Groq only when explicitly requested; it does not affect scoring or route
selection. Live Groq connectivity was not tested without a user-provided key.
