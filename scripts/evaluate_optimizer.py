"""Evaluate the weighted route optimizer against feasible baselines."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.evaluation import evaluate_dataset
from backend.app.services.route_optimizer import load_dataset


def evaluate(data_dir: Path, profile: str = "balanced") -> dict[str, Any]:
    shipments, routes = load_dataset(data_dir)
    return evaluate_dataset(shipments, routes, profile=profile)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    parser.add_argument(
        "--profile",
        choices=("cost_sensitive", "balanced", "time_sensitive", "reliability_sensitive"),
        default="balanced",
    )
    args = parser.parse_args()
    result = evaluate(args.data_dir, args.profile)
    print(f"Profile: {result['profile']}")
    print(f"Shipments: {result['shipment_count']}")
    print(f"With feasible routes: {result['shipments_with_feasible_routes']}")
    print(f"Without feasible routes: {result['shipments_without_feasible_routes']}")
    print(f"Feasibility-label mismatch warnings: {result['feasibility_label_mismatch_warnings']}")
    for name, summary in result["results"].items():
        print(
            f"{name}: selected={summary['count']}, "
            f"feasibility_rate={summary['feasibility_rate']:.2%}, "
            f"constraint_violations={summary['constraint_violations']}, "
            f"average_cost_usd={summary['average_cost_usd']:.2f}, "
            f"average_transit_days={summary['average_transit_days']:.2f}, "
            f"average_risk_penalty={summary['average_risk_penalty']:.6f}, "
            f"average_total_penalty={summary['average_total_penalty']:.6f}"
        )
    print(f"Profile sensitivity: {result['profile_sensitivity']}")
    print(f"Pareto frontier: {result['pareto_frontier']}")
    print(result["interpretation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
