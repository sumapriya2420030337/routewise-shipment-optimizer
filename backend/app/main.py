"""FastAPI application for RouteWise's explainable route optimizer."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.app.schemas import (
    AnalystExplanationResponse,
    DisruptionRequest,
    DisruptionResponse,
    Evaluation,
    Health,
    Metadata,
    NewShipmentOptimizationResponse,
    NewShipmentRequest,
    OptimizeRequest,
    OptimizeResponse,
    RouteCandidate,
    RoutesResponse,
    SensitivityPoint,
    SensitivityRequest,
    SensitivityResponse,
    Shipment,
)
from backend.app.services.evaluation import evaluate_dataset
from backend.app.services.analyst import explain_optimization
from backend.app.services.disruption_simulator import simulate_disruptions
from backend.app.services.new_shipment import optimize_new_shipment
from backend.app.services.route_optimizer import (
    OptimizationInputError,
    optimize_shipment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("ROUTEWISE_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
try:
    import csv

    with (DATA_DIR / "shipments.csv").open(encoding="utf-8", newline="") as file:
        SHIPMENTS: list[dict[str, str]] = list(csv.DictReader(file))
    with (DATA_DIR / "routes.csv").open(encoding="utf-8", newline="") as file:
        ROUTES: list[dict[str, str]] = list(csv.DictReader(file))
except OSError as exc:
    raise RuntimeError(f"Could not load RouteWise dataset from {DATA_DIR}: {exc}") from exc

try:
    _INITIAL_EVALUATION = evaluate_dataset(SHIPMENTS, ROUTES)
except (OptimizationInputError, ValueError) as exc:
    raise RuntimeError(f"RouteWise dataset failed validation: {exc}") from exc

app = FastAPI(
    title="RouteWise API",
    description=(
        "Explainable shipment route optimization over synthetic candidate data. "
        "Feasibility is computed from hard constraints; stored labels are audit targets."
    ),
    version="1.0.0",
)
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ROUTEWISE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _compute(shipment_id: str, profile: str = "balanced", **kwargs: Any) -> dict[str, Any]:
    try:
        return optimize_shipment(
            shipment_id,
            SHIPMENTS,
            ROUTES,
            profile=profile,
            **kwargs,
        )
    except OptimizationInputError as exc:
        if str(exc).startswith("Unknown shipment_id"):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _shipment_response(row: dict[str, str]) -> Shipment:
    result = _compute(row["shipment_id"])
    route_count = sum(route["shipment_id"] == row["shipment_id"] for route in ROUTES)
    return Shipment(
        shipment_id=row["shipment_id"],
        origin=row["origin"],
        destination=row["destination"],
        cargo_type=row["cargo_type"],
        weight_kg=float(row["weight_kg"]),
        distance_km=float(row["distance_km"]),
        max_cost_usd=float(row["max_cost_usd"]),
        max_transit_days=float(row["max_transit_days"]),
        max_delay_probability=float(row["max_delay_probability"]),
        max_congestion_risk=float(row["max_congestion_risk"]),
        max_geopolitical_risk=float(row["max_geopolitical_risk"]),
        scenario_class=row["scenario_class"],
        candidate_route_count=route_count,
        computed_status=(
            "feasible" if result["status"] == "recommended" else "no_feasible_route"
        ),
    )


@app.get("/api/v1/health", response_model=Health, tags=["System"])
def health() -> Health:
    return Health(
        status="ok",
        dataset_status="loaded",
        shipment_count=len(SHIPMENTS),
        route_count=len(ROUTES),
    )


@app.get("/api/v1/metadata", response_model=Metadata, tags=["System"])
def metadata() -> Metadata:
    route_modes = dict(sorted(Counter(route["route_mode"] for route in ROUTES).items()))
    feasible_routes = sum(
        route["is_feasible"] is True
        for shipment in SHIPMENTS
        for route in _compute(shipment["shipment_id"])["ranked_routes"]
    )
    return Metadata(
        synthetic_data=True,
        shipment_count=len(SHIPMENTS),
        route_count=len(ROUTES),
        feasible_route_count=feasible_routes,
        infeasible_route_count=len(ROUTES) - feasible_routes,
        shipments_with_feasible_routes=_INITIAL_EVALUATION[
            "shipments_with_feasible_routes"
        ],
        shipments_without_feasible_routes=_INITIAL_EVALUATION[
            "shipments_without_feasible_routes"
        ],
        route_modes=route_modes,
        evaluation=Evaluation(**_INITIAL_EVALUATION),
    )


@app.get("/api/v1/shipments", response_model=list[Shipment], tags=["Shipments"])
def list_shipments(
    search: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, pattern="^(feasible|no_feasible_route)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Shipment]:
    rows = SHIPMENTS
    if search:
        needle = search.casefold()
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                row[field] for field in ("shipment_id", "origin", "destination", "cargo_type")
            ).casefold()
        ]
    result = [_shipment_response(row) for row in rows]
    if status:
        result = [shipment for shipment in result if shipment.computed_status == status]
    return result[offset : offset + limit]


@app.get(
    "/api/v1/shipments/{shipment_id}",
    response_model=Shipment,
    tags=["Shipments"],
)
def get_shipment(shipment_id: str) -> Shipment:
    row = next((item for item in SHIPMENTS if item["shipment_id"] == shipment_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown shipment_id {shipment_id!r}")
    return _shipment_response(row)


@app.get(
    "/api/v1/shipments/{shipment_id}/routes",
    response_model=RoutesResponse,
    tags=["Shipments"],
)
def get_shipment_routes(shipment_id: str) -> RoutesResponse:
    result = _compute(shipment_id)
    routes: list[RouteCandidate] = []
    for ranked in result["ranked_routes"]:
        routes.append(
            RouteCandidate(
                route_id=ranked["route_id"],
                shipment_id=ranked["shipment_id"],
                route_mode=ranked["route_mode"],
                cost_usd=ranked["cost_usd"],
                transit_time_days=ranked["transit_time_days"],
                delay_probability=ranked["delay_probability"],
                congestion_risk=ranked["congestion_risk"],
                geopolitical_risk=ranked["geopolitical_risk"],
                stored_is_feasible=ranked["stored_is_feasible"],
                is_feasible=True,
                feasibility_status="feasible",
                rank=ranked["rank"],
                total_penalty=ranked["total_penalty"],
            )
        )
    for rejected in result["rejected_routes"]:
        routes.append(
            RouteCandidate(
                route_id=rejected["route_id"],
                shipment_id=rejected["shipment_id"],
                route_mode=rejected["route_mode"],
                cost_usd=rejected["cost_usd"],
                transit_time_days=rejected["transit_time_days"],
                delay_probability=rejected["delay_probability"],
                congestion_risk=rejected["congestion_risk"],
                geopolitical_risk=rejected["geopolitical_risk"],
                stored_is_feasible=rejected["stored_is_feasible"],
                is_feasible=False,
                feasibility_status="infeasible",
                rejection_reasons=rejected["rejection_reasons"],
            )
        )
    routes.sort(key=lambda route: (not route.is_feasible, route.rank or 0, route.route_id))
    return RoutesResponse(
        shipment_id=shipment_id,
        status=result["status"],
        routes=routes,
    )


@app.post(
    "/api/v1/optimize",
    response_model=OptimizeResponse,
    tags=["Optimization"],
)
def optimize(request: OptimizeRequest) -> OptimizeResponse:
    overrides = (
        request.constraint_overrides.as_overrides()
        if request.constraint_overrides
        else None
    )
    result = _compute(
        request.shipment_id,
        profile=request.profile,
        weights=request.weights.model_dump() if request.weights else None,
        constraint_overrides=overrides,
    )
    return OptimizeResponse(**result)


@app.post(
    "/api/v1/shipments/optimize-new",
    response_model=NewShipmentOptimizationResponse,
    tags=["Shipments"],
    summary="Create a transient shipment and optimize its candidate routes",
)
def optimize_new_shipment_request(
    request: NewShipmentRequest,
) -> NewShipmentOptimizationResponse:
    payload = request.model_dump(exclude_none=True)
    try:
        result = optimize_new_shipment(payload)
    except OptimizationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return NewShipmentOptimizationResponse(**result)


@app.post(
    "/api/v1/analyst/explanation",
    response_model=AnalystExplanationResponse,
    tags=["Optimization"],
    summary="Explain a computed recommendation with optional Groq commentary",
)
async def analyst_explanation(
    request: OptimizeRequest,
) -> AnalystExplanationResponse:
    overrides = (
        request.constraint_overrides.as_overrides()
        if request.constraint_overrides
        else None
    )
    result = _compute(
        request.shipment_id,
        profile=request.profile,
        weights=request.weights.model_dump() if request.weights else None,
        constraint_overrides=overrides,
    )
    return await explain_optimization(result)


@app.post(
    "/api/v1/sensitivity",
    response_model=SensitivityResponse,
    tags=["Optimization"],
)
def sensitivity(request: SensitivityRequest) -> SensitivityResponse:
    overrides = (
        request.constraint_overrides.as_overrides()
        if request.constraint_overrides
        else None
    )
    points: list[SensitivityPoint] = []
    selected_ids: list[str | None] = []
    for point_weights in request.weight_sets:
        result = _compute(
            request.shipment_id,
            weights=point_weights.model_dump(),
            constraint_overrides=overrides,
        )
        recommendation = result["recommendation"]
        selected_id = recommendation["route_id"] if recommendation else None
        selected_ids.append(selected_id)
        points.append(
            SensitivityPoint(
                weights=point_weights,
                status=result["status"],
                selected_route_id=selected_id,
                total_penalty=(
                    recommendation["total_penalty"] if recommendation else None
                ),
            )
        )
    counts = Counter(route_id for route_id in selected_ids if route_id is not None)
    if not selected_ids or not any(selected_ids):
        stability = 1.0
    else:
        stability = max(counts.values()) / len(selected_ids)
    changes = sum(
        selected_ids[index] != selected_ids[index - 1]
        for index in range(1, len(selected_ids))
    )
    return SensitivityResponse(
        shipment_id=request.shipment_id,
        points=points,
        recommendation_counts=dict(sorted(counts.items())),
        recommendation_stability=round(stability, 4),
        route_changes_between_adjacent_points=changes,
        explanation=(
            f"The most common recommendation appears in {stability:.0%} of the "
            f"{len(points)} tested weight combinations; {changes} adjacent "
            "weight changes selected a different route."
        ),
    )


@app.post(
    "/api/v1/simulate-disruption",
    response_model=DisruptionResponse,
    tags=["Disruption simulation"],
    summary="Re-optimize a shipment after hypothetical route disruptions",
)
def simulate_disruption(request: DisruptionRequest) -> DisruptionResponse:
    try:
        result = simulate_disruptions(
            request.shipment_id,
            SHIPMENTS,
            ROUTES,
            [scenario.model_dump() for scenario in request.scenarios],
            profile=request.profile,
            weights=request.weights.model_dump() if request.weights else None,
            constraint_overrides=(
                request.constraint_overrides.as_overrides()
                if request.constraint_overrides
                else None
            ),
        )
    except OptimizationInputError as exc:
        if str(exc).startswith("Unknown shipment_id"):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DisruptionResponse(**result)


@app.get("/openapi.json", include_in_schema=False)
def openapi_schema() -> dict[str, Any]:
    return app.openapi()
