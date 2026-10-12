from __future__ import annotations

import copy
import math
import unittest

from backend.app.services.disruption_simulator import simulate_disruptions
from backend.app.services.route_optimizer import OptimizationInputError


SHIPMENTS = [
    {
        "shipment_id": "S1",
        "origin": "Los Angeles, US",
        "destination": "New York, US",
        "cargo_type": "machinery",
        "weight_kg": 100,
        "distance_km": 500,
        "max_cost_usd": 500,
        "max_transit_days": 10,
        "max_delay_probability": 0.6,
        "max_congestion_risk": 0.6,
        "max_geopolitical_risk": 0.6,
        "scenario_class": "feasible",
    }
]

ROUTES = [
    {
        "route_id": "A",
        "shipment_id": "S1",
        "route_mode": "road",
        "cost_usd": 100,
        "transit_time_days": 2,
        "delay_probability": 0.2,
        "congestion_risk": 0.2,
        "geopolitical_risk": 0.2,
        "is_feasible": "true",
    },
    {
        "route_id": "B",
        "shipment_id": "S1",
        "route_mode": "rail",
        "cost_usd": 300,
        "transit_time_days": 5,
        "delay_probability": 0.3,
        "congestion_risk": 0.3,
        "geopolitical_risk": 0.3,
        "is_feasible": "true",
    },
    {
        "route_id": "C",
        "shipment_id": "S1",
        "route_mode": "air",
        "cost_usd": 600,
        "transit_time_days": 1,
        "delay_probability": 0.1,
        "congestion_risk": 0.1,
        "geopolitical_risk": 0.1,
        "is_feasible": "false",
    },
]


class DisruptionSimulatorTests(unittest.TestCase):
    def test_probability_risk_time_and_cost_transformations_are_applied_and_capped(self) -> None:
        scenarios = [
            {
                "name": "probability",
                "delay_probability_increase": 0.7,
                "route_ids": ["A"],
            },
            {
                "name": "congestion",
                "congestion_risk_increase": 0.2,
                "route_modes": ["rail"],
            },
            {
                "name": "geopolitical",
                "geopolitical_risk_increase": 0.1,
                "route_modes": ["road"],
            },
            {
                "name": "time",
                "transit_time_increase_pct": 0.5,
                "route_ids": ["A"],
            },
            {
                "name": "cost",
                "cost_increase_pct": 0.25,
                "route_ids": ["A"],
            },
            {
                "name": "cap",
                "delay_probability_increase": 1,
                "route_ids": ["A"],
            },
        ]
        result = simulate_disruptions("S1", SHIPMENTS, ROUTES, scenarios)
        by_name = {scenario["name"]: scenario for scenario in result["scenarios"]}
        by_id = {
            scenario["name"]: {
                route["route_id"]: route for route in scenario["routes"]
            }
            for scenario in result["scenarios"]
        }
        self.assertAlmostEqual(
            by_id["probability"]["A"]["disrupted_metrics"]["delay_probability"],
            0.9,
        )
        self.assertAlmostEqual(by_id["congestion"]["B"]["disrupted_metrics"]["congestion_risk"], 0.5)
        self.assertAlmostEqual(
            by_id["geopolitical"]["A"]["disrupted_metrics"]["geopolitical_risk"],
            0.3,
        )
        self.assertAlmostEqual(
            by_id["time"]["A"]["disrupted_metrics"]["transit_time_days"], 3.0
        )
        self.assertAlmostEqual(by_id["cost"]["A"]["disrupted_metrics"]["cost_usd"], 125.0)
        self.assertAlmostEqual(
            by_id["cap"]["A"]["disrupted_metrics"]["delay_probability"], 1.0
        )
        self.assertEqual(
            by_name["probability"]["parameters"]["affected_route_ids"], ["A"]
        )

    def test_source_inputs_are_unchanged_and_repeated_scenarios_are_deterministic(self) -> None:
        shipments_before = copy.deepcopy(SHIPMENTS)
        routes_before = copy.deepcopy(ROUTES)
        scenario = [{"name": "cost shock", "cost_increase_pct": 0.5}]
        first = simulate_disruptions("S1", SHIPMENTS, ROUTES, scenario)
        second = simulate_disruptions("S1", SHIPMENTS, ROUTES, scenario)
        self.assertEqual(first, second)
        self.assertEqual(SHIPMENTS, shipments_before)
        self.assertEqual(ROUTES, routes_before)
        self.assertTrue(first["hypothetical"])

    def test_disrupted_original_becomes_infeasible_and_optimizer_selects_fallback(self) -> None:
        result = simulate_disruptions(
            "S1",
            SHIPMENTS,
            ROUTES,
            [{"name": "road cost shock", "cost_increase_pct": 5, "route_ids": ["A"]}],
        )
        scenario = result["scenarios"][0]
        self.assertEqual(result["baseline"]["recommendation"]["route_id"], "A")
        self.assertEqual(scenario["status"], "recommended")
        self.assertEqual(scenario["recommendation"]["route_id"], "B")
        self.assertTrue(scenario["comparison"]["fallback_available"])
        self.assertFalse(
            scenario["comparison"]["original_recommendation_remains_feasible"]
        )
        route_a = next(route for route in scenario["routes"] if route["route_id"] == "A")
        self.assertIn("cost_usd", route_a["disrupted_rejection_reasons"][0])

    def test_disruption_can_leave_no_feasible_fallback(self) -> None:
        result = simulate_disruptions(
            "S1",
            SHIPMENTS,
            ROUTES,
            [{"name": "network cost shock", "cost_increase_pct": 5}],
        )
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["status"], "no_feasible_route")
        self.assertIsNone(scenario["recommendation"])
        self.assertFalse(scenario["comparison"]["fallback_available"])
        self.assertEqual(scenario["comparison"]["feasible_candidate_count"], 0)
        self.assertEqual(len(scenario["rejected_routes"]), 3)

    def test_disruption_reoptimization_preserves_geographic_rejections(self) -> None:
        shipment = copy.deepcopy(SHIPMENTS[0])
        shipment.update(
            origin="Tokyo, JP",
            destination="Mumbai, IN",
            max_cost_usd=1000,
            max_transit_days=10,
        )
        routes = copy.deepcopy(ROUTES)
        routes[0]["route_mode"] = "road"
        routes[1]["route_mode"] = "rail"
        routes[2]["route_mode"] = "air"
        result = simulate_disruptions(
            "S1",
            [shipment],
            routes,
            [{"name": "base case"}],
        )
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["recommendation"]["route_mode"], "air")
        rejected_by_mode = {
            route["route_mode"]: route for route in scenario["rejected_routes"]
        }
        self.assertIn(
            "geographic",
            " ".join(rejected_by_mode["road"]["rejection_reasons"]),
        )
        self.assertIn(
            "geographic",
            " ".join(rejected_by_mode["rail"]["rejection_reasons"]),
        )

    def test_validation_rejects_unknown_shipment_and_route_selector(self) -> None:
        with self.assertRaisesRegex(OptimizationInputError, "Unknown shipment_id"):
            simulate_disruptions(
                "S999", SHIPMENTS, ROUTES, [{"name": "baseline"}]
            )
        with self.assertRaisesRegex(OptimizationInputError, "not belonging"):
            simulate_disruptions(
                "S1",
                SHIPMENTS,
                ROUTES,
                [{"name": "invalid route", "route_ids": ["OTHER"]}],
            )

    def test_validation_rejects_invalid_scenario_ranges_and_duplicate_names(self) -> None:
        for scenario in (
            {"name": "invalid", "cost_increase_pct": math.nan},
            {"name": "invalid", "delay_probability_increase": 1.1},
            {"name": "invalid", "route_modes": ["teleport"]},
        ):
            with self.subTest(scenario=scenario):
                with self.assertRaises(OptimizationInputError):
                    simulate_disruptions("S1", SHIPMENTS, ROUTES, [scenario])
        with self.assertRaisesRegex(OptimizationInputError, "unique"):
            simulate_disruptions(
                "S1",
                SHIPMENTS,
                ROUTES,
                [{"name": "same"}, {"name": "SAME"}],
            )

    def test_mode_and_route_filters_intersect(self) -> None:
        with self.assertRaisesRegex(OptimizationInputError, "match no routes"):
            simulate_disruptions(
                "S1",
                SHIPMENTS,
                ROUTES,
                [
                    {
                        "name": "intersection",
                        "cost_increase_pct": 1,
                        "route_modes": ["road"],
                        "route_ids": ["B"],
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
