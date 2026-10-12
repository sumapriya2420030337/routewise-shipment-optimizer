"""Create transient shipments and illustrative candidate routes for optimization."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping
from typing import Any

from backend.app.services.geography import transport_mode_rejection_reason
from backend.app.services.route_optimizer import optimize_shipment

_MODES = ("ocean", "rail", "road", "air")
_MODE_ESTIMATES = {
    "ocean": (0.56, 0.92, 0.18, 0.20, 0.14),
    "rail": (0.72, 0.84, 0.13, 0.15, 0.12),
    "road": (0.91, 0.69, 0.15, 0.18, 0.20),
    "air": (0.96, 0.53, 0.10, 0.27, 0.24),
}


def optimize_new_shipment(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic transient shipment and delegate scoring to the optimizer."""
    values = dict(payload)
    overrides = values.pop("constraint_overrides", None) or {}
    weights = values.pop("weights", None)
    profile = values.pop("profile", "balanced")
    supplied_routes = values.pop("candidate_routes", None)

    identity = {
        key: values[key]
        for key in (
            "origin",
            "destination",
            "cargo_type",
            "weight_kg",
            "max_cost_usd",
            "max_transit_days",
            "max_delay_probability",
            "max_congestion_risk",
            "max_geopolitical_risk",
        )
    }
    canonical = json.dumps(
        {"shipment": identity, "candidate_routes": supplied_routes},
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:10].upper()
    shipment_id = f"NEW-{fingerprint}"
    rng = random.Random(int(fingerprint, 16))
    estimated_distance_km = round(rng.uniform(250.0, 12_000.0), 1)

    shipment = {
        "shipment_id": shipment_id,
        **identity,
        "distance_km": estimated_distance_km,
        "scenario_class": "feasible",
    }
    if supplied_routes is None:
        available_modes = [
            mode for mode in _MODES
            if transport_mode_rejection_reason(
                identity["origin"], identity["destination"], mode
            ) is None
        ]
        route_rows = [
            {
                "route_id": f"{shipment_id}-R{index + 1}",
                "shipment_id": shipment_id,
                "route_mode": mode,
                "cost_usd": round(
                    identity["max_cost_usd"] * _MODE_ESTIMATES[mode][0], 2
                ),
                "transit_time_days": round(
                    identity["max_transit_days"] * _MODE_ESTIMATES[mode][1], 2
                ),
                "delay_probability": round(
                    min(1.0, _MODE_ESTIMATES[mode][2] + rng.uniform(0.0, 0.06)), 4
                ),
                "congestion_risk": round(
                    min(1.0, _MODE_ESTIMATES[mode][3] + rng.uniform(0.0, 0.06)), 4
                ),
                "geopolitical_risk": round(
                    min(1.0, _MODE_ESTIMATES[mode][4] + rng.uniform(0.0, 0.06)), 4
                ),
            }
            for index, mode in enumerate(available_modes)
        ]
        route_source = "synthetic_estimates"
    else:
        route_rows = [
            {
                "route_id": f"{shipment_id}-R{index + 1}",
                "shipment_id": shipment_id,
                **route,
            }
            for index, route in enumerate(supplied_routes)
        ]
        route_source = "user_supplied"

    effective_constraints = {**identity, **overrides}
    eligible = any(
        route["cost_usd"] <= effective_constraints["max_cost_usd"]
        and route["transit_time_days"] <= effective_constraints["max_transit_days"]
        and route["delay_probability"]
        <= effective_constraints["max_delay_probability"]
        and route["congestion_risk"]
        <= effective_constraints["max_congestion_risk"]
        and route["geopolitical_risk"]
        <= effective_constraints["max_geopolitical_risk"]
        and transport_mode_rejection_reason(
            identity["origin"], identity["destination"], route["route_mode"]
        ) is None
        for route in route_rows
    )
    shipment["scenario_class"] = "feasible" if eligible else "infeasible"
    for route in route_rows:
        route["is_feasible"] = (
            route["cost_usd"] <= effective_constraints["max_cost_usd"]
            and route["transit_time_days"] <= effective_constraints["max_transit_days"]
            and route["delay_probability"]
            <= effective_constraints["max_delay_probability"]
            and route["congestion_risk"]
            <= effective_constraints["max_congestion_risk"]
            and route["geopolitical_risk"]
            <= effective_constraints["max_geopolitical_risk"]
            and transport_mode_rejection_reason(
                identity["origin"], identity["destination"], route["route_mode"]
            ) is None
        )

    optimization = optimize_shipment(
        shipment_id,
        [shipment],
        route_rows,
        profile=profile,
        weights=weights,
        constraint_overrides=overrides,
    )
    return {
        "shipment": {
            "shipment_id": shipment_id,
            **identity,
            "estimated_distance_km": estimated_distance_km,
        },
        "candidate_route_source": route_source,
        "synthetic_estimates": route_source == "synthetic_estimates",
        "persistence": "request_only",
        "optimization": optimization,
    }
