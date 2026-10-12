"""Deterministic hypothetical route disruptions built on the route optimizer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from backend.app.services.route_optimizer import (
    OptimizationInputError,
    optimize_shipment,
)

PROBABILITY_METRICS = (
    "delay_probability",
    "congestion_risk",
    "geopolitical_risk",
)
PERCENTAGE_METRICS = {
    "transit_time_increase_pct": "transit_time_days",
    "cost_increase_pct": "cost_usd",
}
SCENARIO_LIMITS = {
    "delay_probability_increase": 1.0,
    "congestion_risk_increase": 1.0,
    "geopolitical_risk_increase": 1.0,
    "transit_time_increase_pct": 5.0,
    "cost_increase_pct": 5.0,
}
VALID_ROUTE_MODES = {"air", "ocean", "rail", "road"}


def _validate_scenarios(scenarios: Sequence[Mapping[str, object]]) -> None:
    names: set[str] = set()
    for index, scenario in enumerate(scenarios, start=1):
        name = scenario.get("name")
        if not isinstance(name, str) or not name.strip():
            raise OptimizationInputError(
                f"Scenario {index} must have a non-empty name"
            )
        normalized_name = name.casefold()
        if normalized_name in names:
            raise OptimizationInputError(
                f"Scenario names must be unique: {name!r}"
            )
        names.add(normalized_name)

        for parameter, maximum in SCENARIO_LIMITS.items():
            value = scenario.get(parameter, 0.0)
            if isinstance(value, bool):
                raise OptimizationInputError(
                    f"Scenario {name!r} parameter {parameter} must be numeric"
                )
            try:
                numeric_value = float(value)
            except (TypeError, ValueError) as exc:
                raise OptimizationInputError(
                    f"Scenario {name!r} parameter {parameter} must be numeric"
                ) from exc
            if not math.isfinite(numeric_value) or not 0 <= numeric_value <= maximum:
                raise OptimizationInputError(
                    f"Scenario {name!r} parameter {parameter} must be between "
                    f"0 and {maximum:g}"
                )

        modes = scenario.get("route_modes", [])
        route_ids = scenario.get("route_ids", [])
        if not isinstance(modes, (list, tuple)) or len(modes) > 4:
            raise OptimizationInputError(
                f"Scenario {name!r} route_modes must contain at most four modes"
            )
        if any(
            not isinstance(mode, str) or mode not in VALID_ROUTE_MODES
            for mode in modes
        ):
            raise OptimizationInputError(
                f"Scenario {name!r} contains an unsupported route mode"
            )
        if len(set(modes)) != len(modes):
            raise OptimizationInputError(
                f"Scenario {name!r} route_modes must not contain duplicates"
            )
        if not isinstance(route_ids, (list, tuple)) or len(route_ids) > 4:
            raise OptimizationInputError(
                f"Scenario {name!r} route_ids must contain at most four IDs"
            )
        if any(not isinstance(route_id, str) or not route_id.strip() for route_id in route_ids):
            raise OptimizationInputError(
                f"Scenario {name!r} route_ids must be non-empty strings"
            )
        if len(set(route_ids)) != len(route_ids):
            raise OptimizationInputError(
                f"Scenario {name!r} route_ids must not contain duplicates"
            )


def _selected_for_disruption(
    route: Mapping[str, object],
    route_modes: Sequence[str],
    route_ids: Sequence[str],
) -> bool:
    if route_ids and str(route["route_id"]) not in route_ids:
        return False
    if route_modes and str(route["route_mode"]) not in route_modes:
        return False
    return True


def _route_results(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    eligible = {
        route["route_id"]: {
            **route,
            "is_feasible": True,
            "rejection_reasons": [],
        }
        for route in result["ranked_routes"]
    }
    rejected = {
        route["route_id"]: {
            **route,
            "is_feasible": False,
        }
        for route in result["rejected_routes"]
    }
    return {**eligible, **rejected}


def _apply_scenario(
    routes: Sequence[Mapping[str, object]],
    shipment_id: str,
    scenario: Mapping[str, object],
) -> tuple[list[dict[str, object]], set[str]]:
    route_modes = list(scenario.get("route_modes", []))
    route_ids = list(scenario.get("route_ids", []))
    matching_ids = {
        str(route["route_id"])
        for route in routes
        if route["shipment_id"] == shipment_id
        and _selected_for_disruption(route, route_modes, route_ids)
    }
    known_ids = {
        str(route["route_id"])
        for route in routes
        if route["shipment_id"] == shipment_id
    }
    unknown_ids = set(route_ids) - known_ids
    if unknown_ids:
        raise OptimizationInputError(
            f"Scenario references route IDs not belonging to shipment "
            f"{shipment_id!r}: {sorted(unknown_ids)}"
        )
    if (route_modes or route_ids) and not matching_ids:
        raise OptimizationInputError(
            f"Scenario selectors match no routes for shipment {shipment_id!r}"
        )

    transformed: list[dict[str, object]] = []
    for source in routes:
        route = dict(source)
        if route["shipment_id"] == shipment_id and str(route["route_id"]) in matching_ids:
            for metric in PROBABILITY_METRICS:
                increase = float(scenario.get(f"{metric}_increase", 0.0))
                route[metric] = min(1.0, float(route[metric]) + increase)
            for parameter, metric in PERCENTAGE_METRICS.items():
                increase_pct = float(scenario.get(parameter, 0.0))
                route[metric] = float(route[metric]) * (1.0 + increase_pct)
        transformed.append(route)
    return transformed, matching_ids


def _evaluated_routes(
    baseline_routes: Mapping[str, Mapping[str, Any]],
    disrupted_routes: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for route_id, baseline in baseline_routes.items():
        disrupted = disrupted_routes[route_id]
        changed_metrics = {
            metric: {
                "baseline": baseline[metric],
                "disrupted": disrupted[metric],
            }
            for metric in (
                "cost_usd",
                "transit_time_days",
                *PROBABILITY_METRICS,
            )
            if baseline[metric] != disrupted[metric]
        }
        output.append(
            {
                "route_id": route_id,
                "route_mode": baseline["route_mode"],
                "baseline_metrics": {
                    metric: baseline[metric]
                    for metric in ("cost_usd", "transit_time_days", *PROBABILITY_METRICS)
                },
                "disrupted_metrics": {
                    metric: disrupted[metric]
                    for metric in ("cost_usd", "transit_time_days", *PROBABILITY_METRICS)
                },
                "baseline_feasible": baseline["is_feasible"],
                "disrupted_feasible": disrupted["is_feasible"],
                "baseline_rejection_reasons": baseline.get("rejection_reasons", []),
                "disrupted_rejection_reasons": disrupted.get("rejection_reasons", []),
                "baseline_rank": baseline.get("rank"),
                "disrupted_rank": disrupted.get("rank"),
                "baseline_penalty": baseline.get("total_penalty"),
                "disrupted_penalty": disrupted.get("total_penalty"),
                "changed_metrics": changed_metrics,
            }
        )
    return output


def simulate_disruptions(
    shipment_id: str,
    shipments: Sequence[Mapping[str, object]],
    routes: Sequence[Mapping[str, object]],
    scenarios: Sequence[Mapping[str, object]],
    *,
    profile: str = "balanced",
    weights: Mapping[str, object] | None = None,
    constraint_overrides: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Re-optimize copied route records for named, bounded hypothetical scenarios."""
    if not scenarios:
        raise OptimizationInputError("At least one disruption scenario is required")
    _validate_scenarios(scenarios)
    baseline_result = optimize_shipment(
        shipment_id,
        shipments,
        routes,
        profile=profile,
        weights=weights,
        constraint_overrides=constraint_overrides,
    )
    baseline_by_id = _route_results(baseline_result)
    baseline_recommendation = baseline_result["recommendation"]
    candidate_count = len(baseline_by_id)
    scenario_results: list[dict[str, Any]] = []

    for scenario in scenarios:
        transformed_routes, affected_ids = _apply_scenario(routes, shipment_id, scenario)
        disrupted_result = optimize_shipment(
            shipment_id,
            shipments,
            transformed_routes,
            profile=profile,
            weights=weights,
            constraint_overrides=constraint_overrides,
        )
        disrupted_by_id = _route_results(disrupted_result)
        recommendation = disrupted_result["recommendation"]
        original_route_id = (
            baseline_recommendation["route_id"] if baseline_recommendation else None
        )
        original_route_after_disruption = (
            disrupted_by_id.get(original_route_id) if original_route_id else None
        )
        baseline_candidate_count = sum(
            bool(route["is_feasible"]) for route in baseline_by_id.values()
        )
        disrupted_candidate_count = sum(
            bool(route["is_feasible"]) for route in disrupted_by_id.values()
        )
        selected_route_changed = (
            baseline_recommendation["route_id"] if baseline_recommendation else None
        ) != (recommendation["route_id"] if recommendation else None)
        comparison = {
            "original_recommendation_route_id": original_route_id,
            "disrupted_recommendation_route_id": (
                recommendation["route_id"] if recommendation else None
            ),
            "original_recommendation_remains_feasible": bool(
                original_route_after_disruption
                and original_route_after_disruption["is_feasible"]
            ),
            "recommendation_changed": selected_route_changed,
            "feasible_candidate_count": disrupted_candidate_count,
            "feasible_candidate_percentage": round(
                disrupted_candidate_count / candidate_count * 100, 2
            ) if candidate_count else 0.0,
            "baseline_feasible_candidate_count": baseline_candidate_count,
            "feasible_candidate_change": (
                disrupted_candidate_count - baseline_candidate_count
            ),
            "fallback_available": bool(
                recommendation
                and original_route_id
                and recommendation["route_id"] != original_route_id
            ),
            "recommended_cost_change_usd": (
                round(
                    recommendation["cost_usd"] - baseline_recommendation["cost_usd"],
                    2,
                )
                if recommendation and baseline_recommendation
                else None
            ),
            "recommended_transit_time_change_days": (
                round(
                    recommendation["transit_time_days"]
                    - baseline_recommendation["transit_time_days"],
                    2,
                )
                if recommendation and baseline_recommendation
                else None
            ),
            "recommended_risk_penalty_change": (
                round(
                    recommendation["risk_penalty"]
                    - baseline_recommendation["risk_penalty"],
                    6,
                )
                if recommendation and baseline_recommendation
                else None
            ),
        }
        if not recommendation:
            summary = (
                f"No feasible route remains after scenario {scenario['name']!r}; "
                f"{disrupted_candidate_count} of {candidate_count} candidates meet "
                "all recomputed constraints."
            )
        elif not baseline_recommendation:
            summary = (
                f"Scenario {scenario['name']!r} leaves {disrupted_candidate_count} "
                f"of {candidate_count} candidates feasible; route "
                f"{recommendation['route_id']} is recommended."
            )
        elif comparison["fallback_available"]:
            summary = (
                f"Original route {original_route_id} "
                f"{'remains feasible but was outranked' if comparison['original_recommendation_remains_feasible'] else 'is no longer feasible'}; "
                f"fallback route {recommendation['route_id']} is recommended. "
                f"{disrupted_candidate_count} of {candidate_count} candidates remain feasible."
            )
        else:
            summary = (
                f"Original route {original_route_id or 'none'} remains the "
                f"recommendation. {disrupted_candidate_count} of {candidate_count} "
                "candidates meet all recomputed constraints."
            )
        scenario_results.append(
            {
                "name": scenario["name"],
                "parameters": {
                    "delay_probability_increase": scenario.get(
                        "delay_probability_increase", 0.0
                    ),
                    "congestion_risk_increase": scenario.get(
                        "congestion_risk_increase", 0.0
                    ),
                    "geopolitical_risk_increase": scenario.get(
                        "geopolitical_risk_increase", 0.0
                    ),
                    "transit_time_increase_pct": scenario.get(
                        "transit_time_increase_pct", 0.0
                    ),
                    "cost_increase_pct": scenario.get("cost_increase_pct", 0.0),
                    "route_modes": list(scenario.get("route_modes", [])),
                    "route_ids": list(scenario.get("route_ids", [])),
                    "affected_route_ids": sorted(affected_ids),
                },
                "status": disrupted_result["status"],
                "recommendation": recommendation,
                "ranked_routes": disrupted_result["ranked_routes"],
                "rejected_routes": disrupted_result["rejected_routes"],
                "comparison": comparison,
                "routes": _evaluated_routes(baseline_by_id, disrupted_by_id),
                "summary": summary,
            }
        )

    return {
        "shipment_id": shipment_id,
        "hypothetical": True,
        "profile": baseline_result["profile"],
        "weights": baseline_result["weights"],
        "baseline": {
            "status": baseline_result["status"],
            "recommendation": baseline_recommendation,
            "ranked_routes": baseline_result["ranked_routes"],
            "rejected_routes": baseline_result["rejected_routes"],
            "feasible_candidate_count": sum(
                bool(route["is_feasible"]) for route in baseline_by_id.values()
            ),
            "candidate_count": candidate_count,
        },
        "scenarios": scenario_results,
        "assumptions": [
            "Disruptions are hypothetical deterministic transformations, not forecasts.",
            "Probability and risk increments are additive and capped at 1.0.",
            "Cost and transit-time increases are multiplicative percentage increases.",
            "The source shipment and route records are not mutated.",
        ],
    }
