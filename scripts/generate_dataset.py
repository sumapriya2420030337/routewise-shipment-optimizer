"""Generate RouteWise's deterministic synthetic shipment and route dataset.

Field definitions and units
---------------------------
Shipments:
* shipment_id: unique synthetic shipment identifier.
* origin, destination: city and country labels.
* cargo_type: synthetic cargo category.
* weight_kg: shipment mass in kilograms.
* distance_km: approximate lane distance in kilometers.
* max_cost_usd: maximum acceptable route cost in US dollars.
* max_transit_days: maximum acceptable transit duration in days.
* max_delay_probability: maximum acceptable delay probability, from 0 to 1.
* max_congestion_risk: maximum acceptable congestion risk, from 0 to 1.
* max_geopolitical_risk: maximum acceptable geopolitical risk, from 0 to 1.
* scenario_class: feasible means at least one route meets all limits; infeasible
  means none do. It describes the generated scenario, not an optimizer choice.

Routes:
* route_id: unique synthetic candidate route identifier.
* shipment_id: identifier of the shipment this candidate serves.
* route_mode: air, ocean, rail, or road.
* cost_usd: estimated route cost in US dollars.
* transit_time_days: estimated transit duration in days.
* delay_probability, congestion_risk, geopolitical_risk: unitless values from
  0 to 1, inclusive.
* is_feasible: whether this route satisfies every limit on its shipment.

Only Python's standard library is used. Candidate route metrics are sampled
without ranking or selecting a preferred route. Scenario generation uses
rejection sampling so both feasible and infeasible examples are present.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path
import sys
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.services.geography import transport_mode_rejection_reason

DEFAULT_SEED = 2026
SHIPMENT_COUNT = 30
MAX_ROUTES_PER_SHIPMENT = 4
SCENARIO_COUNTS = {"feasible": 20, "infeasible": 10}
MAX_ROUTE_SAMPLE_ATTEMPTS = 100

SHIPMENT_FIELDS = [
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
]
ROUTE_FIELDS = [
    "route_id",
    "shipment_id",
    "route_mode",
    "cost_usd",
    "transit_time_days",
    "delay_probability",
    "congestion_risk",
    "geopolitical_risk",
    "is_feasible",
]

LOCATIONS = [
    ("Los Angeles", "US"),
    ("New York", "US"),
    ("Vancouver", "CA"),
    ("Toronto", "CA"),
    ("Mexico City", "MX"),
    ("Sao Paulo", "BR"),
    ("London", "GB"),
    ("Rotterdam", "NL"),
    ("Hamburg", "DE"),
    ("Istanbul", "TR"),
    ("Dubai", "AE"),
    ("Mumbai", "IN"),
    ("Singapore", "SG"),
    ("Shanghai", "CN"),
    ("Tokyo", "JP"),
    ("Sydney", "AU"),
]
CARGO_TYPES = ["electronics", "machinery", "textiles", "medical_supplies", "food"]
ROUTE_MODES = {
    "air": {"per_kg_km": 0.00125, "per_km": 0.12, "speed_km_day": 650, "delay": (0.03, 0.48)},
    "ocean": {"per_kg_km": 0.00018, "per_km": 0.08, "speed_km_day": 350, "delay": (0.12, 0.82)},
    "rail": {"per_kg_km": 0.00036, "per_km": 0.10, "speed_km_day": 500, "delay": (0.08, 0.68)},
    "road": {"per_kg_km": 0.00048, "per_km": 0.11, "speed_km_day": 550, "delay": (0.04, 0.62)},
}

SHIPMENT_NUMERIC_RANGES: dict[str, tuple[float, float | None, bool]] = {
    "weight_kg": (0.0, None, False),
    "distance_km": (0.0, None, False),
    "max_cost_usd": (0.0, None, False),
    "max_transit_days": (0.0, None, False),
    "max_delay_probability": (0.0, 1.0, True),
    "max_congestion_risk": (0.0, 1.0, True),
    "max_geopolitical_risk": (0.0, 1.0, True),
}
ROUTE_NUMERIC_RANGES: dict[str, tuple[float, float | None, bool]] = {
    "cost_usd": (0.0, None, False),
    "transit_time_days": (0.0, None, False),
    "delay_probability": (0.0, 1.0, True),
    "congestion_risk": (0.0, 1.0, True),
    "geopolitical_risk": (0.0, 1.0, True),
}


def route_is_feasible(shipment: dict[str, object], route: dict[str, object]) -> bool:
    """Return whether all route metrics meet the shipment's declared limits."""
    return (
        transport_mode_rejection_reason(
            str(shipment["origin"]),
            str(shipment["destination"]),
            str(route["route_mode"]),
        ) is None
        and float(route["cost_usd"]) <= float(shipment["max_cost_usd"])
        and float(route["transit_time_days"]) <= float(shipment["max_transit_days"])
        and float(route["delay_probability"]) <= float(shipment["max_delay_probability"])
        and float(route["congestion_risk"]) <= float(shipment["max_congestion_risk"])
        and float(route["geopolitical_risk"]) <= float(shipment["max_geopolitical_risk"])
    )


def _sample_route_metrics(
    rng: random.Random,
    mode: str,
    weight_kg: float,
    distance_km: float,
) -> dict[str, object]:
    """Sample one mode's metrics without comparing it to other candidates."""
    parameters = ROUTE_MODES[mode]
    cost = (
        distance_km * (weight_kg * parameters["per_kg_km"] + parameters["per_km"])
        + rng.uniform(100.0, 700.0)
    )
    transit_time = distance_km / parameters["speed_km_day"] + rng.uniform(0.5, 8.0)
    return {
        "route_mode": mode,
        "cost_usd": round(cost, 2),
        "transit_time_days": round(transit_time, 2),
        "delay_probability": round(rng.uniform(*parameters["delay"]), 4),
        "congestion_risk": round(rng.uniform(0.03, 0.97), 4),
        "geopolitical_risk": round(rng.uniform(0.02, 0.96), 4),
    }


def _sample_candidate_routes(
    rng: random.Random,
    shipment: dict[str, object],
    first_route_number: int,
) -> list[dict[str, object]]:
    """Re-sample the full candidate set until it matches its scenario class."""
    expected_feasibility = shipment["scenario_class"] == "feasible"
    modes = [
        mode for mode in ROUTE_MODES
        if transport_mode_rejection_reason(
            str(shipment["origin"]), str(shipment["destination"]), mode
        ) is None
    ]
    if not modes:
        raise ValueError(
            f"No supported direct transport modes for {shipment['shipment_id']}"
        )
    for _ in range(MAX_ROUTE_SAMPLE_ATTEMPTS):
        candidate_modes = list(modes)
        rng.shuffle(candidate_modes)
        candidates = []
        for offset, mode in enumerate(candidate_modes):
            metrics = _sample_route_metrics(
                rng,
                mode,
                float(shipment["weight_kg"]),
                float(shipment["distance_km"]),
            )
            candidates.append(
                {
                    "route_id": f"R{first_route_number + offset:04d}",
                    "shipment_id": shipment["shipment_id"],
                    **metrics,
                    "is_feasible": str(route_is_feasible(shipment, metrics)).lower(),
                }
            )

        has_feasible_route = any(route["is_feasible"] == "true" for route in candidates)
        if has_feasible_route == expected_feasibility:
            return candidates

    if expected_feasibility:
        # A lane with only one physically supported mode can make the original
        # random limits impossible to satisfy. Broaden the limits around one
        # seeded candidate without ranking it; the optimizer remains the only
        # component that chooses a recommendation.
        selected = rng.choice(candidates)
        for metric, limit in (
            ("cost_usd", "max_cost_usd"),
            ("transit_time_days", "max_transit_days"),
            ("delay_probability", "max_delay_probability"),
            ("congestion_risk", "max_congestion_risk"),
            ("geopolitical_risk", "max_geopolitical_risk"),
        ):
            shipment[limit] = max(float(shipment[limit]), float(selected[metric]))
    else:
        # Preserve the requested infeasible scenario if random sampling could
        # not produce one within the bounded attempt count.
        shipment["max_cost_usd"] = min(
            float(shipment["max_cost_usd"]),
            min(float(route["cost_usd"]) for route in candidates) / 2,
        )

    for route in candidates:
        route["is_feasible"] = str(route_is_feasible(shipment, route)).lower()
    return candidates


def generate_dataset(seed: int = DEFAULT_SEED) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Generate shipment and route records reproducibly for the given seed."""
    rng = random.Random(seed)
    scenario_classes = ["feasible"] * SCENARIO_COUNTS["feasible"] + [
        "infeasible"
    ] * SCENARIO_COUNTS["infeasible"]
    rng.shuffle(scenario_classes)

    shipments: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    for index, scenario_class in enumerate(scenario_classes, start=1):
        origin, destination = rng.sample(LOCATIONS, 2)
        weight_kg = round(rng.uniform(50.0, 20_000.0), 2)
        distance_km = round(rng.uniform(250.0, 12_000.0), 1)
        reference_cost = distance_km * (weight_kg * 0.00065 + 0.10) + 400.0

        if scenario_class == "feasible":
            limits = {
                "max_cost_usd": round(reference_cost * rng.uniform(0.85, 1.8), 2),
                "max_transit_days": round(
                    max(4.0, distance_km / 550.0 * rng.uniform(1.3, 3.2) + 4.0), 2
                ),
                "max_delay_probability": round(rng.uniform(0.55, 0.97), 4),
                "max_congestion_risk": round(rng.uniform(0.55, 0.98), 4),
                "max_geopolitical_risk": round(rng.uniform(0.55, 0.98), 4),
            }
        else:
            limits = {
                "max_cost_usd": round(reference_cost * rng.uniform(0.05, 0.30), 2),
                "max_transit_days": round(rng.uniform(1.0, 4.0), 2),
                "max_delay_probability": round(rng.uniform(0.05, 0.35), 4),
                "max_congestion_risk": round(rng.uniform(0.05, 0.35), 4),
                "max_geopolitical_risk": round(rng.uniform(0.05, 0.35), 4),
            }

        shipment: dict[str, object] = {
            "shipment_id": f"S{index:03d}",
            "origin": f"{origin[0]}, {origin[1]}",
            "destination": f"{destination[0]}, {destination[1]}",
            "cargo_type": rng.choice(CARGO_TYPES),
            "weight_kg": weight_kg,
            "distance_km": distance_km,
            **limits,
            "scenario_class": scenario_class,
        }
        shipments.append(shipment)
        routes.extend(_sample_candidate_routes(rng, shipment, len(routes) + 1))

    validate_dataset(shipments, routes)
    return shipments, routes


def _validate_numeric_ranges(
    rows: list[dict[str, object]],
    ranges: dict[str, tuple[float, float | None, bool]],
    record_name: str,
) -> None:
    for row_index, row in enumerate(rows, start=1):
        for field, (minimum, maximum, minimum_is_inclusive) in ranges.items():
            try:
                value = float(row[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"{record_name} row {row_index} has invalid numeric field {field!r}"
                ) from exc
            below_minimum = value < minimum or (value == minimum and not minimum_is_inclusive)
            if not math.isfinite(value) or below_minimum or (maximum is not None and value > maximum):
                raise ValueError(
                    f"{record_name} row {row_index} field {field!r} must be "
                    f"{'>=' if minimum_is_inclusive else '>'} {minimum}"
                    + (f" and <= {maximum}" if maximum is not None else "")
                )


def validate_dataset(
    shipments: list[dict[str, object]],
    routes: list[dict[str, object]],
) -> None:
    """Raise ValueError unless identities, ranges, references, and feasibility agree."""
    if len(shipments) != SHIPMENT_COUNT:
        raise ValueError(f"Expected {SHIPMENT_COUNT} shipment records; got {len(shipments)}")
    if len(routes) < SHIPMENT_COUNT or len(routes) > SHIPMENT_COUNT * MAX_ROUTES_PER_SHIPMENT:
        raise ValueError(
            f"Expected between {SHIPMENT_COUNT} and "
            f"{SHIPMENT_COUNT * MAX_ROUTES_PER_SHIPMENT} route records; got {len(routes)}"
        )

    for row_index, row in enumerate(shipments, start=1):
        missing_fields = set(SHIPMENT_FIELDS) - row.keys()
        if missing_fields:
            raise ValueError(f"Shipment row {row_index} is missing fields: {sorted(missing_fields)}")
        empty_fields = [
            field for field in SHIPMENT_FIELDS
            if not isinstance(row[field], (int, float)) and not str(row[field]).strip()
        ]
        if empty_fields:
            raise ValueError(f"Shipment row {row_index} has empty fields: {empty_fields}")
    for row_index, row in enumerate(routes, start=1):
        missing_fields = set(ROUTE_FIELDS) - row.keys()
        if missing_fields:
            raise ValueError(f"Route row {row_index} is missing fields: {sorted(missing_fields)}")
        empty_fields = [
            field for field in ROUTE_FIELDS
            if not isinstance(row[field], (int, float)) and not str(row[field]).strip()
        ]
        if empty_fields:
            raise ValueError(f"Route row {row_index} has empty fields: {empty_fields}")

    shipment_ids = [str(row.get("shipment_id", "")) for row in shipments]
    route_ids = [str(row.get("route_id", "")) for row in routes]
    if any(not value for value in shipment_ids) or len(set(shipment_ids)) != len(shipment_ids):
        raise ValueError("Shipment IDs must be non-empty and unique")
    if any(not value for value in route_ids) or len(set(route_ids)) != len(route_ids):
        raise ValueError("Route IDs must be non-empty and unique")

    _validate_numeric_ranges(shipments, SHIPMENT_NUMERIC_RANGES, "Shipment")
    _validate_numeric_ranges(routes, ROUTE_NUMERIC_RANGES, "Route")
    shipment_by_id = {str(row["shipment_id"]): row for row in shipments}
    route_counts = {shipment_id: 0 for shipment_id in shipment_by_id}
    feasible_counts = {shipment_id: 0 for shipment_id in shipment_by_id}
    route_modes_by_shipment = {shipment_id: set() for shipment_id in shipment_by_id}

    for route_index, route in enumerate(routes, start=1):
        shipment_id = str(route.get("shipment_id", ""))
        if shipment_id not in shipment_by_id:
            raise ValueError(f"Route row {route_index} references unknown shipment {shipment_id!r}")
        shipment = shipment_by_id[shipment_id]
        route_counts[shipment_id] += 1

        mode = str(route.get("route_mode", ""))
        if mode not in ROUTE_MODES:
            raise ValueError(f"Route row {route_index} has unsupported route mode {mode!r}")
        route_modes_by_shipment[shipment_id].add(mode)
        geographic_reason = transport_mode_rejection_reason(
            str(shipment["origin"]), str(shipment["destination"]), mode
        )
        if geographic_reason:
            raise ValueError(
                f"Route row {route_index} is geographically infeasible: "
                f"{geographic_reason}"
            )

        actual_feasibility = route_is_feasible(shipment, route)
        declared_feasibility = str(route.get("is_feasible", "")).lower() == "true"
        if str(route.get("is_feasible", "")).lower() not in {"true", "false"}:
            raise ValueError(f"Route row {route_index} has invalid is_feasible value")
        if declared_feasibility != actual_feasibility:
            raise ValueError(f"Route row {route_index} has incorrect feasibility label")
        feasible_counts[shipment_id] += int(actual_feasibility)

    for shipment_id, count in route_counts.items():
        if not 1 <= count <= MAX_ROUTES_PER_SHIPMENT:
            raise ValueError(
                f"Shipment {shipment_id} must have 1 to {MAX_ROUTES_PER_SHIPMENT} "
                f"geographically supported routes; got {count}"
            )

        scenario_class = str(shipment_by_id[shipment_id].get("scenario_class", ""))
        if scenario_class not in SCENARIO_COUNTS:
            raise ValueError(f"Shipment {shipment_id} has invalid scenario_class {scenario_class!r}")
        has_feasible_route = feasible_counts[shipment_id] > 0
        if has_feasible_route != (scenario_class == "feasible"):
            raise ValueError(f"Shipment {shipment_id} does not match its scenario_class")

    actual_scenarios = {
        scenario: sum(row["scenario_class"] == scenario for row in shipments)
        for scenario in SCENARIO_COUNTS
    }
    if actual_scenarios != SCENARIO_COUNTS:
        raise ValueError(f"Scenario counts must be {SCENARIO_COUNTS}; got {actual_scenarios}")


def write_dataset(
    shipments: list[dict[str, object]],
    routes: list[dict[str, object]],
    output_dir: Path,
) -> None:
    """Validate records and write the two documented CSV files."""
    validate_dataset(shipments, routes)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, fields, rows in (
        ("shipments.csv", SHIPMENT_FIELDS, shipments),
        ("routes.csv", ROUTE_FIELDS, routes),
    ):
        with (output_dir / filename).open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data",
        help="directory for shipments.csv and routes.csv (default: repository data/)",
    )
    args = parser.parse_args(argv)

    shipments, routes = generate_dataset(seed=args.seed)
    write_dataset(shipments, routes, args.output_dir)
    print(
        f"Generated {len(shipments)} shipments and {len(routes)} routes "
        f"with seed {args.seed} in {args.output_dir.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
