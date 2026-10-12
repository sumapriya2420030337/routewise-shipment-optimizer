from __future__ import annotations

import unittest

from backend.app.services.evaluation import evaluate_dataset


def shipment(shipment_id: str, scenario: str) -> dict[str, object]:
    return {
        "shipment_id": shipment_id,
        "origin": "Los Angeles, US",
        "destination": "New York, US",
        "cargo_type": "machinery",
        "weight_kg": 100.0,
        "distance_km": 500.0,
        "max_cost_usd": 500.0,
        "max_transit_days": 10.0,
        "max_delay_probability": 1.0,
        "max_congestion_risk": 1.0,
        "max_geopolitical_risk": 1.0,
        "scenario_class": scenario,
    }


def route(
    route_id: str,
    shipment_id: str,
    cost: float,
    days: float,
    delay: float,
    feasible: bool = True,
) -> dict[str, object]:
    return {
        "route_id": route_id,
        "shipment_id": shipment_id,
        "route_mode": "road",
        "cost_usd": cost,
        "transit_time_days": days,
        "delay_probability": delay,
        "congestion_risk": delay,
        "geopolitical_risk": delay,
        "is_feasible": str(feasible).lower(),
    }


class EvaluationTests(unittest.TestCase):
    def test_baselines_profile_sensitivity_and_pareto_use_computed_feasible_routes(self) -> None:
        shipments = [shipment("S1", "feasible"), shipment("S2", "infeasible")]
        routes = [
            route("A", "S1", 100.0, 10.0, 0.5),
            route("B", "S1", 300.0, 1.0, 0.4),
            route("C", "S1", 250.0, 5.0, 0.1),
            route("D", "S2", 600.0, 11.0, 0.2, feasible=False),
        ]

        result = evaluate_dataset(shipments, routes)

        self.assertEqual(result["shipments_with_feasible_routes"], 1)
        self.assertEqual(result["shipments_without_feasible_routes"], 1)
        self.assertEqual(set(result["results"]), {
            "weighted_optimizer",
            "cheapest_feasible",
            "fastest_feasible",
            "reliability_oriented",
        })
        self.assertEqual(result["results"]["cheapest_feasible"]["average_cost_usd"], 100.0)
        self.assertEqual(result["results"]["fastest_feasible"]["average_transit_days"], 1.0)
        self.assertEqual(result["results"]["reliability_oriented"]["average_risk_penalty"], 0.1)
        self.assertTrue(
            all(row["constraint_violations"] == 0 for row in result["results"].values())
        )
        self.assertEqual(result["pareto_frontier"]["eligible_route_count"], 3)
        self.assertEqual(result["pareto_frontier"]["non_dominated_route_count"], 3)
        self.assertEqual(set(result["profile_sensitivity"]), {
            "cost_sensitive",
            "balanced",
            "time_sensitive",
            "reliability_sensitive",
        })


if __name__ == "__main__":
    unittest.main()
