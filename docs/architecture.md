# RouteWise architecture

## Components

```text
Browser
  React + TypeScript + Tailwind dashboard
  typed API client (fetch)
       |  /api/* (Vite proxy in development)
       v
FastAPI application
  Pydantic request/response validation
  project-relative CSV loading
       |                         |
       v                         v
route_optimizer.py          evaluation.py
feasibility, ranking,       weighted/baseline summaries,
score breakdowns            profile sensitivity, Pareto counts
       \                         /
        \---- shipments.csv / routes.csv

Disruption Lab
       |
disruption_simulator.py
copy-on-write metric shocks -> route_optimizer revalidation/ranking

Create Shipment
       |
POST /api/v1/shipments/optimize-new
deterministic illustrative route estimates -> route_optimizer

Decision Lab (optional, explicit action)
       |
analyst.py
optimizer-computed facts -> validated Groq commentary
deterministic local fallback when provider unavailable
```

This is a single-process, file-backed application. The optimizer and evaluation
services can be imported and called directly without starting FastAPI. The API
loads both CSV files from the repository-level `data/` directory relative to
`backend/app/main.py`, with an optional `ROUTEWISE_DATA_DIR` override. A missing
file or invalid dataset fails startup with an explicit error.

## Backend boundaries

- `backend/app/main.py` owns HTTP routing, startup loading, CORS, and mapping
  domain input errors to HTTP responses.
- `backend/app/schemas.py` defines strict Pydantic contracts. Unknown fields
  are rejected; weights and supported hard-constraint overrides are bounded.
- `backend/app/services/route_optimizer.py` is the single source of truth for
  validation, computed feasibility, eligible-route normalization, weighted
  ranking, deterministic tie-breaking, rejection reasons, and explanations.
- `backend/app/services/evaluation.py` reuses the optimizer for weighted
  choices and profile comparisons. Cheapest, fastest, and reliability-oriented
  strategies choose only independently computed-feasible candidates.
- `backend/app/services/disruption_simulator.py` creates per-scenario copies of
  route records, applies bounded additive risk or multiplicative cost/time
  changes to selected modes/IDs, then invokes the same optimizer. Its response
  includes baseline/disrupted route metrics and scores, rejection details,
  resilience counts, route changes, and fallback availability; source data
  remains immutable.
- `backend/app/services/new_shipment.py` builds a request-scoped shipment and
  either four deterministic illustrative candidate estimates or uses
  user-supplied candidates. It passes all candidates, profile/weights, and
  supported overrides through `route_optimizer.py`; it does not persist
  shipment records or alter the CSV files. Synthetic distance and route metrics
  are illustrative inputs only, not carrier quotes or real-world forecasts.
- `backend/app/services/analyst.py` optionally turns minimized facts from a
  server-recomputed optimizer result into structured natural-language
  commentary. Groq is called only after an explicit request and only with a
  server-side key. Its response is schema-validated; missing credentials,
  provider errors, or invalid output produce deterministic commentary. It
  never selects routes, changes scores, or makes optimization a provider
  dependency.

Stored feasibility flags and scenario classes are audit labels. They cannot
make a route eligible or ineligible in the optimizer.

## Frontend boundaries

The React app consumes typed API contracts from `frontend/src/types.ts` using
`frontend/src/api.ts`. The UI does not calculate feasibility or authoritative
scores. Search, profile/custom weights, supported constraint overrides,
optimization, and sensitivity analysis are sent to the API. The dashboard's
summary charts are built from the measured metadata response.
The Create Shipment form sends canonical USD constraints to the API and renders
the returned optimizer result; transient shipment details are held only in
React page memory, so refreshing loses them.
The Disruption Lab submits hypothetical scenarios to the simulator API; it does
not independently score routes. Browser preferences are stored locally, and
the activity panel contains only the current page session.

## Runtime and local development

FastAPI serves the API and OpenAPI docs on `127.0.0.1:8000`. Vite serves the
frontend on port `5173` and forwards `/api` requests to the API. The backend
permits the two standard local Vite origins by default; both origins can be
configured with `ROUTEWISE_CORS_ORIGINS`. The core application needs no
external service or model. If explicitly enabled, the optional analyst calls
Groq; it falls back locally when no key or a provider response is unavailable.

See the root README for reproducible Windows setup/run commands and the
evaluation document for the algorithm and observed results.
