"""Measured baseline, sensitivity, constraint-audit, and Pareto evaluation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from backend.app.services.route_optimizer import (
    PROFILES,
    optimize_shipment,
)

BASELINES = (
    "weighted_optimizer",
    "cheapest_feasible",
    "fastest_feasible",
    "reliability_oriented",
)


def _summary(rows: Sequence[Mapping[str, Any]], total_shipments: int) -> dict[str, Any]:
    selected = len(rows)
    return {
        "count": selected,
        "feasibility_rate": round(selected / total_shipments, 4) if total_shipments else 0.0,
        "constraint_violations": sum(not bool(row["is_feasible"]) for row in rows),
        "average_cost_usd": round(
            sum(float(row["cost_usd"]) for row in rows) / selected, 2
        ) if selected else 0.0,
        "average_transit_days": round(
            sum(float(row["transit_time_days"]) for row in rows) / selected, 2
        ) if selected else 0.0,
        "average_risk_penalty": round(
            sum(float(row["risk_penalty"]) for row in rows) / selected, 6
        ) if selected else 0.0,
        "average_total_penalty": round(
            sum(float(row["total_penalty"]) for row in rows) / selected, 6
        ) if selected else 0.0,
    }


def _pareto_routes(routes: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Return non-dominated routes minimizing cost, duration, and risk."""
    frontier: list[Mapping[str, Any]] = []
    for route in routes:
        dominated = any(
            other is not route
            and all(
                float(other[metric]) <= float(route[metric])
                for metric in ("cost_usd", "transit_time_days", "risk_penalty")
            )
            and any(
                float(other[metric]) < float(route[metric])
                for metric in ("cost_usd", "transit_time_days", "risk_penalty")
            )
            for other in routes
        )
        if not dominated:
            frontier.append(route)
    return frontier


def evaluate_dataset(
    shipments: Sequence[Mapping[str, object]],
    routes: Sequence[Mapping[str, object]],
    profile: str = "balanced",
) -> dict[str, Any]:
    """Evaluate four choice strategies using only actual, computed-feasible options."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile {profile!r}")

    selected_by_strategy: dict[str, list[Mapping[str, Any]]] = {
        name: [] for name in BASELINES
    }
    profile_choices: dict[str, Counter[str]] = {
        name: Counter() for name in PROFILES
    }
    feasible_shipment_count = 0
    eligible_route_count = 0
    mismatch_count = 0
    frontier_count = 0
    frontier_sizes: list[int] = []

    for shipment in shipments:
        shipment_id = str(shipment["shipment_id"])
        balanced_result = optimize_shipment(
            shipment_id, shipments, routes, profile=profile
        )
        mismatch_count += len(balanced_result["warnings"])
        if balanced_result["status"] == "no_feasible_route":
            continue
        feasible_shipment_count += 1
        eligible = balanced_result["ranked_routes"]
        eligible_route_count += len(eligible)
        cheapest = min(eligible, key=lambda route: (route["cost_usd"], route["route_id"]))
        fastest = min(
            eligible,
            key=lambda route: (route["transit_time_days"], route["route_id"]),
        )
        reliable = min(
            eligible,
            key=lambda route: (route["risk_penalty"], route["route_id"]),
        )
        selected_by_strategy["weighted_optimizer"].append(
            balanced_result["recommendation"]
        )
        selected_by_strategy["cheapest_feasible"].append(cheapest)
        selected_by_strategy["fastest_feasible"].append(fastest)
        selected_by_strategy["reliability_oriented"].append(reliable)

        frontier = _pareto_routes(eligible)
        frontier_count += len(frontier)
        frontier_sizes.append(len(frontier))
        for profile_name in PROFILES:
            profile_result = optimize_shipment(
                shipment_id, shipments, routes, profile=profile_name
            )
            profile_choices[profile_name][profile_result["recommendation"]["route_id"]] += 1

    total_shipments = len(shipments)
    return {
        "profile": profile,
        "shipment_count": total_shipments,
        "shipments_with_feasible_routes": feasible_shipment_count,
        "shipments_without_feasible_routes": total_shipments - feasible_shipment_count,
        "feasibility_label_mismatch_warnings": mismatch_count,
        "results": {
            name: _summary(rows, total_shipments)
            for name, rows in selected_by_strategy.items()
        },
        "profile_sensitivity": {
            name: dict(sorted(counts.items())) for name, counts in profile_choices.items()
        },
        "pareto_frontier": {
            "eligible_route_count": eligible_route_count,
            "non_dominated_route_count": frontier_count,
            "average_frontier_size_per_feasible_shipment": round(
                sum(frontier_sizes) / len(frontier_sizes), 2
            ) if frontier_sizes else 0.0,
        },
        "interpretation": (
            "Descriptive outcomes on synthetic data; baselines are not ground truth. "
            "All selected routes satisfy recomputed hard constraints."
        ),
    }
