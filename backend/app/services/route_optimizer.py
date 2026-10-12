"""Deterministic, explainable shipment-route optimization.

The CSV's precomputed ``is_feasible`` and ``scenario_class`` values are audit
targets only. Eligibility is recomputed from the shipment's hard maximum cost,
transit-time, delay, congestion, and geopolitical-risk limits.

Cost and transit time are min-max normalized across eligible candidate routes
for each shipment. Identical values map to 0.5 (neutral). Risk is an unscaled
weighted sum of three unit-interval metrics:
0.50 * delay + 0.25 * congestion + 0.25 * geopolitical risk.
The risk coefficients are illustrative assumptions, not calibrated estimates.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from backend.app.services.geography import transport_mode_rejection_reason

WEIGHT_SUM_TOLERANCE = 1e-9
RISK_COEFFICIENTS = {
    "delay_probability": 0.50,
    "congestion_risk": 0.25,
    "geopolitical_risk": 0.25,
}
PROFILES: dict[str, dict[str, float]] = {
    "cost_sensitive": {"cost": 0.60, "time": 0.15, "risk": 0.25},
    "balanced": {"cost": 0.40, "time": 0.30, "risk": 0.30},
    "time_sensitive": {"cost": 0.15, "time": 0.60, "risk": 0.25},
    "reliability_sensitive": {"cost": 0.15, "time": 0.15, "risk": 0.70},
}

SHIPMENT_REQUIRED_FIELDS = {
    "shipment_id",
    "origin",
    "destination",
    "cargo_type",
    "weight_kg",
    "distance_km",
    "max_cost_usd",
    "max_transit_days",
    "max_delay_probability",
    "max_congestion_risk",
    "max_geopolitical_risk",
    "scenario_class",
}
ROUTE_REQUIRED_FIELDS = {
    "route_id",
    "shipment_id",
    "route_mode",
    "cost_usd",
    "transit_time_days",
    "delay_probability",
    "congestion_risk",
    "geopolitical_risk",
    "is_feasible",
}
RISK_LIMIT_FIELDS = (
    ("delay_probability", "max_delay_probability"),
    ("congestion_risk", "max_congestion_risk"),
    ("geopolitical_risk", "max_geopolitical_risk"),
)


class OptimizationInputError(ValueError):
    """Raised when shipment or candidate-route input violates the CSV contract."""


def _required_text(row: Mapping[str, object], field: str, record: str) -> str:
    value = row.get(field)
    if value is None or not str(value).strip():
        raise OptimizationInputError(f"{record} field {field!r} is required")
    return str(value).strip()


def _number(
    row: Mapping[str, object],
    field: str,
    record: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw_value = row.get(field)
    if raw_value is None or isinstance(raw_value, bool) or not str(raw_value).strip():
        raise OptimizationInputError(f"{record} field {field!r} must be a number")
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise OptimizationInputError(
            f"{record} field {field!r} must be a number"
        ) from exc
    if not math.isfinite(value):
        raise OptimizationInputError(f"{record} field {field!r} must be finite")
    if minimum is not None and value < minimum:
        raise OptimizationInputError(f"{record} field {field!r} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise OptimizationInputError(f"{record} field {field!r} must be <= {maximum}")
    return value


def _flag(row: Mapping[str, object], field: str, record: str) -> bool:
    value = row.get(field)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower() if value is not None else ""
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise OptimizationInputError(f"{record} field {field!r} must be true or false")


def _validate_weights(weights: Mapping[str, object]) -> dict[str, float]:
    expected = {"cost", "time", "risk"}
    if set(weights) != expected:
        raise OptimizationInputError(
            f"Weights must contain exactly {sorted(expected)}"
        )
    validated: dict[str, float] = {}
    for component in sorted(expected):
        value = weights[component]
        if isinstance(value, bool):
            raise OptimizationInputError(f"Weight {component!r} must be a finite number")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise OptimizationInputError(
                f"Weight {component!r} must be a finite number"
            ) from exc
        if not math.isfinite(numeric_value) or numeric_value < 0:
            raise OptimizationInputError(
                f"Weight {component!r} must be finite and nonnegative"
            )
        validated[component] = numeric_value
    total = sum(validated.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=WEIGHT_SUM_TOLERANCE):
        raise OptimizationInputError(
            f"Weights must sum to 1 within {WEIGHT_SUM_TOLERANCE:g}; got {total:.12g}"
        )
    return validated


def _validated_records(
    shipments: Sequence[Mapping[str, object]],
    routes: Sequence[Mapping[str, object]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not shipments:
        raise OptimizationInputError("At least one shipment record is required")

    indexed_shipments: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(shipments, start=1):
        record = f"Shipment row {index}"
        missing = SHIPMENT_REQUIRED_FIELDS - row.keys()
        if missing:
            raise OptimizationInputError(f"{record} missing fields: {sorted(missing)}")
        shipment_id = _required_text(row, "shipment_id", record)
        if shipment_id in indexed_shipments:
            raise OptimizationInputError(f"Duplicate shipment_id {shipment_id!r}")

        shipment: dict[str, Any] = {
            "shipment_id": shipment_id,
            "origin": _required_text(row, "origin", record),
            "destination": _required_text(row, "destination", record),
            "cargo_type": _required_text(row, "cargo_type", record),
            "weight_kg": _number(row, "weight_kg", record, minimum=0.0),
            "distance_km": _number(row, "distance_km", record, minimum=0.0),
            "max_cost_usd": _number(row, "max_cost_usd", record, minimum=0.0),
            "max_transit_days": _number(row, "max_transit_days", record, minimum=0.0),
            "max_delay_probability": _number(
                row, "max_delay_probability", record, minimum=0.0, maximum=1.0
            ),
            "max_congestion_risk": _number(
                row, "max_congestion_risk", record, minimum=0.0, maximum=1.0
            ),
            "max_geopolitical_risk": _number(
                row, "max_geopolitical_risk", record, minimum=0.0, maximum=1.0
            ),
            "scenario_class": _required_text(row, "scenario_class", record),
        }
        if shipment["weight_kg"] <= 0 or shipment["distance_km"] <= 0:
            raise OptimizationInputError(
                f"{record} weight_kg and distance_km must be positive"
            )
        if shipment["max_cost_usd"] <= 0 or shipment["max_transit_days"] <= 0:
            raise OptimizationInputError(
                f"{record} max_cost_usd and max_transit_days must be positive"
            )
        if shipment["scenario_class"] not in {"feasible", "infeasible"}:
            raise OptimizationInputError(
                f"{record} scenario_class must be feasible or infeasible"
            )
        indexed_shipments[shipment_id] = shipment

    indexed_routes: list[dict[str, Any]] = []
    route_ids: set[str] = set()
    for index, row in enumerate(routes, start=1):
        record = f"Route row {index}"
        missing = ROUTE_REQUIRED_FIELDS - row.keys()
        if missing:
            raise OptimizationInputError(f"{record} missing fields: {sorted(missing)}")
        route_id = _required_text(row, "route_id", record)
        if route_id in route_ids:
            raise OptimizationInputError(f"Duplicate route_id {route_id!r}")
        route_ids.add(route_id)
        shipment_id = _required_text(row, "shipment_id", record)
        if shipment_id not in indexed_shipments:
            raise OptimizationInputError(
                f"{record} references unknown shipment_id {shipment_id!r}"
            )
        indexed_routes.append(
            {
                "route_id": route_id,
                "shipment_id": shipment_id,
                "route_mode": _required_text(row, "route_mode", record),
                "cost_usd": _number(row, "cost_usd", record, minimum=0.0),
                "transit_time_days": _number(
                    row, "transit_time_days", record, minimum=0.0
                ),
                "delay_probability": _number(
                    row, "delay_probability", record, minimum=0.0, maximum=1.0
                ),
                "congestion_risk": _number(
                    row, "congestion_risk", record, minimum=0.0, maximum=1.0
                ),
                "geopolitical_risk": _number(
                    row, "geopolitical_risk", record, minimum=0.0, maximum=1.0
                ),
                "stored_is_feasible": _flag(row, "is_feasible", record),
            }
        )
        if indexed_routes[-1]["cost_usd"] <= 0 or indexed_routes[-1]["transit_time_days"] <= 0:
            raise OptimizationInputError(
                f"{record} cost_usd and transit_time_days must be positive"
            )
    return indexed_shipments, indexed_routes


def _route_rejection_reasons(
    shipment: Mapping[str, Any], route: Mapping[str, Any]
) -> list[str]:
    reasons: list[str] = []
    geographic_reason = transport_mode_rejection_reason(
        shipment["origin"], shipment["destination"], route["route_mode"]
    )
    if geographic_reason:
        reasons.append(geographic_reason)
    if route["cost_usd"] > shipment["max_cost_usd"]:
        reasons.append(
            f"cost_usd ${route['cost_usd']:.2f} exceeds budget "
            f"${shipment['max_cost_usd']:.2f}"
        )
    if route["transit_time_days"] > shipment["max_transit_days"]:
        reasons.append(
            f"transit_time_days {route['transit_time_days']:.2f} exceeds deadline "
            f"{shipment['max_transit_days']:.2f} days"
        )
    for route_field, limit_field in RISK_LIMIT_FIELDS:
        if route[route_field] > shipment[limit_field]:
            reasons.append(
                f"{route_field} {route[route_field]:.4f} exceeds limit "
                f"{shipment[limit_field]:.4f}"
            )
    return reasons


def _min_max_normalize(value: float, values: Sequence[float]) -> float:
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return 0.5
    return (value - minimum) / (maximum - minimum)


def _score_route(
    route: Mapping[str, Any],
    cost_values: Sequence[float],
    time_values: Sequence[float],
    weights: Mapping[str, float],
) -> dict[str, Any]:
    normalized_cost = _min_max_normalize(route["cost_usd"], cost_values)
    normalized_time = _min_max_normalize(route["transit_time_days"], time_values)
    risk_components = {
        field: route[field] * coefficient
        for field, coefficient in RISK_COEFFICIENTS.items()
    }
    risk_penalty = sum(risk_components.values())
    contributions = {
        "cost": weights["cost"] * normalized_cost,
        "time": weights["time"] * normalized_time,
        "risk": weights["risk"] * risk_penalty,
    }
    displayed_contributions = {
        name: round(value, 6) for name, value in contributions.items()
    }
    total_penalty = round(sum(displayed_contributions.values()), 6)
    return {
        **route,
        "feasibility_status": "feasible",
        "total_cost_usd": round(route["cost_usd"], 2),
        "transit_time_days": round(route["transit_time_days"], 2),
        "risk_components": {
            field: round(value, 6) for field, value in risk_components.items()
        },
        "risk_penalty": round(risk_penalty, 6),
        "normalized_scores": {
            "cost": round(normalized_cost, 6),
            "time": round(normalized_time, 6),
            "risk": round(risk_penalty, 6),
        },
        "weighted_contributions": displayed_contributions,
        "total_penalty": total_penalty,
    }


def optimize_shipment(
    shipment_id: str,
    shipments: Sequence[Mapping[str, object]],
    routes: Sequence[Mapping[str, object]],
    *,
    profile: str = "balanced",
    weights: Mapping[str, object] | None = None,
    constraint_overrides: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Rank feasible routes for one shipment and return a structured explanation.

    ``weights`` optionally overrides the named profile and must contain
    ``cost``, ``time``, and ``risk`` values that are nonnegative and sum to one
    within ``WEIGHT_SUM_TOLERANCE``.
    """
    if profile not in PROFILES:
        raise OptimizationInputError(
            f"Unknown profile {profile!r}; choose one of {sorted(PROFILES)}"
        )
    active_weights = _validate_weights(weights if weights is not None else PROFILES[profile])
    shipment_index, route_records = _validated_records(shipments, routes)
    normalized_shipment_id = str(shipment_id).strip()
    if normalized_shipment_id not in shipment_index:
        raise OptimizationInputError(f"Unknown shipment_id {normalized_shipment_id!r}")

    shipment = shipment_index[normalized_shipment_id]
    shipment = dict(shipment)
    if constraint_overrides is not None:
        allowed_overrides = {
            "max_cost_usd",
            "max_transit_days",
            "max_delay_probability",
            "max_congestion_risk",
            "max_geopolitical_risk",
        }
        unknown_overrides = set(constraint_overrides) - allowed_overrides
        if unknown_overrides:
            raise OptimizationInputError(
                f"Unsupported constraint overrides: {sorted(unknown_overrides)}"
            )
        for field, value in constraint_overrides.items():
            upper_bound = 1.0 if field.startswith("max_") and field.endswith("_risk") else (
                1.0 if field == "max_delay_probability" else None
            )
            minimum = 0.0
            validated_value = _number(
                {field: value},
                field,
                "Constraint override",
                minimum=minimum,
                maximum=upper_bound,
            )
            if field in {"max_cost_usd", "max_transit_days"} and validated_value <= 0:
                raise OptimizationInputError(
                    f"Constraint override {field!r} must be positive"
                )
            shipment[field] = validated_value

    candidates = [r for r in route_records if r["shipment_id"] == normalized_shipment_id]

    feasible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[str] = []
    for candidate in candidates:
        reasons = _route_rejection_reasons(shipment, candidate)
        computed_feasible = not reasons
        if candidate["stored_is_feasible"] != computed_feasible:
            warnings.append(
                f"Route {candidate['route_id']} stored is_feasible="
                f"{str(candidate['stored_is_feasible']).lower()} but computed feasibility is "
                f"{str(computed_feasible).lower()}; computed value is used."
            )
        candidate["is_feasible"] = computed_feasible
        if computed_feasible:
            feasible.append(candidate)
        else:
            rejected.append(
                {
                    **candidate,
                    "feasibility_status": "infeasible",
                    "rejection_reasons": reasons,
                }
            )

    has_feasible_candidate = bool(feasible)
    scenario_matches = (shipment["scenario_class"] == "feasible") == has_feasible_candidate
    if not scenario_matches:
        warnings.append(
            f"Shipment {normalized_shipment_id} stored scenario_class="
            f"{shipment['scenario_class']!r} disagrees with computed feasibility; "
            "computed value is used."
        )

    constraints = {
        "max_cost_usd": shipment["max_cost_usd"],
        "max_transit_days": shipment["max_transit_days"],
        "max_delay_probability": shipment["max_delay_probability"],
        "max_congestion_risk": shipment["max_congestion_risk"],
        "max_geopolitical_risk": shipment["max_geopolitical_risk"],
    }
    common_result = {
        "shipment_id": normalized_shipment_id,
        "profile": profile if weights is None else "custom",
        "weights": active_weights,
        "constraints": constraints,
        "risk_model": {
            "coefficients": dict(RISK_COEFFICIENTS),
            "assumption": "Illustrative risk coefficients; not calibrated estimates.",
        },
        "normalization": (
            "Min-max among feasible candidate routes for this shipment; "
            "identical values map to 0.5."
        ),
        "warnings": warnings,
    }
    if not feasible:
        explanation = (
            "No candidate satisfies all declared shipment limits and geographic "
            "transport-feasibility rules. No route is recommended."
            if rejected
            else (
                "No transport alternatives could be validated for this shipment "
                "in the offline city catalog. No route is recommended."
            )
        )
        return {
            **common_result,
            "status": "no_feasible_route",
            "recommendation": None,
            "ranked_routes": [],
            "rejected_routes": rejected,
            "explanation": explanation,
        }

    costs = [route["cost_usd"] for route in feasible]
    times = [route["transit_time_days"] for route in feasible]
    ranked = [
        _score_route(route, costs, times, active_weights) for route in feasible
    ]
    ranked.sort(key=lambda route: (route["total_penalty"], route["route_id"]))
    for rank, route in enumerate(ranked, start=1):
        route["rank"] = rank
    assumptions = [
        "Risk coefficients are illustrative and not calibrated estimates.",
        "Cost and transit-time normalization is shipment-local and uses only feasible routes.",
        "Identical metric values map to a neutral normalized score of 0.5.",
        "A stored feasibility label is an audit target; computed constraints decide eligibility.",
    ]
    for route in ranked:
        lower_ranked = [
            {
                "route_id": other["route_id"],
                "rank": other["rank"],
                "reason": (
                    f"Ranked lower because its total penalty "
                    f"{other['total_penalty']:.6f} exceeds this route's "
                    f"{route['total_penalty']:.6f}."
                ),
            }
            for other in ranked[route["rank"] :]
        ]
        route["competing_routes_ranked_lower"] = lower_ranked
        route["active_weights"] = dict(active_weights)
        route["active_constraints"] = constraints
        route["assumptions"] = assumptions
        route["explanation"] = (
            f"{'Selected' if route['rank'] == 1 else 'Ranked ' + str(route['rank'])} "
            f"{route['route_id']} among feasible routes: ${route['total_cost_usd']:.2f}, "
            f"{route['transit_time_days']:.2f} days, penalty "
            f"{route['total_penalty']:.6f}."
        )
    winner = ranked[0]
    return {
        **common_result,
        "status": "recommended",
        "recommendation": winner,
        "ranked_routes": ranked,
        "rejected_routes": rejected,
        "explanation": winner["explanation"],
    }


def load_dataset(
    data_dir: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Load the existing shipment/routes CSV pair without changing its schema."""
    loaded: list[list[dict[str, str]]] = []
    for filename, required_fields in (
        ("shipments.csv", SHIPMENT_REQUIRED_FIELDS),
        ("routes.csv", ROUTE_REQUIRED_FIELDS),
    ):
        path = data_dir / filename
        try:
            with path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                if reader.fieldnames is None:
                    raise OptimizationInputError(f"{path} is missing a CSV header")
                missing_fields = required_fields - set(reader.fieldnames)
                if missing_fields:
                    raise OptimizationInputError(
                        f"{path} missing columns: {sorted(missing_fields)}"
                    )
                rows = list(reader)
        except OSError as exc:
            raise OptimizationInputError(f"Could not read {path}: {exc}") from exc
        loaded.append(rows)
    return loaded[0], loaded[1]
