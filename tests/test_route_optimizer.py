from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from backend.app.services.route_optimizer import (
    OptimizationInputError,
    PROFILES,
    optimize_shipment,
)


def make_shipment(**overrides: object) -> dict[str, object]:
    shipment: dict[str, object] = {
        "shipment_id": "S1",
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
        "scenario_class": "feasible",
    }
    shipment.update(overrides)
    return shipment


def make_route(
    route_id: str,
    *,
    cost: float,
    time: float,
    delay: float = 0.2,
    congestion: float = 0.4,
    geopolitical: float = 0.8,
    is_feasible: str = "true",
    **overrides: object,
) -> dict[str, object]:
    route: dict[str, object] = {
        "route_id": route_id,
        "shipment_id": "S1",
        "route_mode": "road",
        "cost_usd": cost,
        "transit_time_days": time,
        "delay_probability": delay,
        "congestion_risk": congestion,
        "geopolitical_risk": geopolitical,
        "is_feasible": is_feasible,
    }
    route.update(overrides)
    return route


def known_example():
    shipment = make_shipment()
    routes = [
        make_route("R1", cost=100.0, time=2.0),
        make_route("R2", cost=300.0, time=6.0, delay=0.4, congestion=0.4, geopolitical=0.4),
        make_route("R3", cost=200.0, time=4.0, delay=0.1, congestion=0.2, geopolitical=0.3),
    ]
    return [shipment], routes


class RouteOptimizerTests(unittest.TestCase):
    def test_known_risk_and_weighted_scoring_example(self) -> None:
        shipments, routes = known_example()
        result = optimize_shipment(
            "S1", shipments, routes, weights={"cost": 0.5, "time": 0.3, "risk": 0.2}
        )
        route = next(item for item in result["ranked_routes"] if item["route_id"] == "R1")

        self.assertEqual(route["risk_components"], {
            "delay_probability": 0.1,
            "congestion_risk": 0.1,
            "geopolitical_risk": 0.2,
        })
        self.assertEqual(route["risk_penalty"], 0.4)
        self.assertEqual(route["weighted_contributions"], {
            "cost": 0.0,
            "time": 0.0,
            "risk": 0.08,
        })
        self.assertEqual(route["total_penalty"], 0.08)

    def test_cost_and_time_min_max_normalization(self) -> None:
        shipments, routes = known_example()
        result = optimize_shipment(
            "S1", shipments, routes, weights={"cost": 1.0, "time": 0.0, "risk": 0.0}
        )
        by_id = {route["route_id"]: route for route in result["ranked_routes"]}

        self.assertEqual(by_id["R1"]["normalized_scores"]["cost"], 0.0)
        self.assertEqual(by_id["R2"]["normalized_scores"]["cost"], 1.0)
        self.assertEqual(by_id["R3"]["normalized_scores"]["cost"], 0.5)
        self.assertEqual(by_id["R3"]["normalized_scores"]["time"], 0.5)

    def test_identical_metrics_use_neutral_normalized_scores(self) -> None:
        shipment = make_shipment()
        routes = [make_route("R2", cost=100.0, time=2.0), make_route("R1", cost=100.0, time=2.0)]
        result = optimize_shipment("S1", [shipment], routes)

        self.assertTrue(all(r["normalized_scores"]["cost"] == 0.5 for r in result["ranked_routes"]))
        self.assertTrue(all(r["normalized_scores"]["time"] == 0.5 for r in result["ranked_routes"]))

    def test_named_profiles_and_custom_weight_validation(self) -> None:
        shipments, routes = known_example()
        for profile in PROFILES:
            self.assertEqual(
                sum(optimize_shipment("S1", shipments, routes, profile=profile)["weights"].values()),
                1.0,
            )
        for weights in (
            {"cost": -0.1, "time": 0.5, "risk": 0.6},
            {"cost": 0.2, "time": 0.2, "risk": 0.2},
            {"cost": float("nan"), "time": 0.5, "risk": 0.5},
            {"cost": 0.5, "time": 0.5},
        ):
            with self.subTest(weights=weights), self.assertRaises(OptimizationInputError):
                optimize_shipment("S1", shipments, routes, weights=weights)

    def test_invalid_risk_metric_rejected(self) -> None:
        shipments, routes = known_example()
        routes[0]["delay_probability"] = 1.01

        with self.assertRaisesRegex(OptimizationInputError, "delay_probability"):
            optimize_shipment("S1", shipments, routes)

    def test_budget_and_deadline_violations_are_reasons_for_rejection(self) -> None:
        shipment = make_shipment(max_cost_usd=100.0, max_transit_days=3.0)
        route = make_route("R1", cost=101.0, time=4.0)
        result = optimize_shipment("S1", [shipment], [route])

        self.assertEqual(result["status"], "no_feasible_route")
        reasons = result["rejected_routes"][0]["rejection_reasons"]
        self.assertTrue(any("exceeds budget" in reason for reason in reasons))
        self.assertTrue(any("exceeds deadline" in reason for reason in reasons))

    def test_risk_caps_are_also_mandatory_and_reasons_are_reported(self) -> None:
        shipment = make_shipment(max_delay_probability=0.1)
        route = make_route("R1", cost=50.0, time=2.0, delay=0.2)
        result = optimize_shipment("S1", [shipment], [route])

        self.assertEqual(result["status"], "no_feasible_route")
        self.assertIn("delay_probability", result["rejected_routes"][0]["rejection_reasons"][0])

    def test_no_feasible_routes_returns_every_candidate_rejection(self) -> None:
        shipment = make_shipment(max_cost_usd=10.0, max_transit_days=1.0)
        routes = [
            make_route("R1", cost=20.0, time=2.0),
            make_route("R2", cost=30.0, time=3.0),
        ]
        result = optimize_shipment("S1", [shipment], routes)

        self.assertEqual(result["status"], "no_feasible_route")
        self.assertIsNone(result["recommendation"])
        self.assertEqual(len(result["rejected_routes"]), 2)
        self.assertTrue(all(route["rejection_reasons"] for route in result["rejected_routes"]))

    def test_equal_penalties_break_ties_by_route_id(self) -> None:
        shipment = make_shipment()
        routes = [
            make_route("R9", cost=100.0, time=2.0),
            make_route("R1", cost=100.0, time=2.0),
        ]
        first = optimize_shipment("S1", [shipment], routes)
        second = optimize_shipment("S1", [shipment], routes)

        self.assertEqual(first, second)
        self.assertEqual(first["recommendation"]["route_id"], "R1")

    def test_explanation_contributions_match_displayed_total(self) -> None:
        shipments, routes = known_example()
        result = optimize_shipment("S1", shipments, routes)
        for route in result["ranked_routes"]:
            self.assertEqual(
                round(sum(route["weighted_contributions"].values()), 6),
                route["total_penalty"],
            )
        self.assertTrue(result["recommendation"]["active_constraints"])
        self.assertTrue(result["recommendation"]["assumptions"])
        self.assertTrue(result["recommendation"]["explanation"])

    def test_unknown_shipment_missing_fields_and_malformed_values_rejected(self) -> None:
        shipments, routes = known_example()
        with self.assertRaisesRegex(OptimizationInputError, "Unknown shipment_id"):
            optimize_shipment("S404", shipments, routes)

        missing = deepcopy(shipments)
        del missing[0]["max_cost_usd"]
        with self.assertRaisesRegex(OptimizationInputError, "missing fields"):
            optimize_shipment("S1", missing, routes)

        malformed = deepcopy(routes)
        malformed[0]["cost_usd"] = "not-a-number"
        with self.assertRaisesRegex(OptimizationInputError, "cost_usd"):
            optimize_shipment("S1", shipments, malformed)

    def test_stored_labels_are_audited_but_not_used_to_choose_feasibility(self) -> None:
        shipment = make_shipment(scenario_class="infeasible")
        route = make_route("R1", cost=10.0, time=1.0, is_feasible="false")
        result = optimize_shipment("S1", [shipment], [route])

        self.assertEqual(result["status"], "recommended")
        self.assertEqual(result["recommendation"]["route_id"], "R1")
        self.assertTrue(result["recommendation"]["is_feasible"])
        self.assertFalse(result["recommendation"]["stored_is_feasible"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_unknown_referenced_shipment_rejected(self) -> None:
        shipments, routes = known_example()
        routes[0]["shipment_id"] = "S404"

        with self.assertRaisesRegex(OptimizationInputError, "unknown shipment_id"):
            optimize_shipment("S1", shipments, routes)

    def test_geography_blocks_tokyo_mumbai_road_and_rail_before_scoring(self) -> None:
        shipment = make_shipment(
            origin="Tokyo, JP",
            destination="Mumbai, IN",
            max_cost_usd=1_000_000,
            max_transit_days=100,
        )
        routes = [
            make_route("ROAD", cost=1, time=1, route_mode="road"),
            make_route("RAIL", cost=2, time=2, route_mode="rail"),
            make_route("OCEAN", cost=3, time=3, route_mode="ocean"),
            make_route("AIR", cost=4, time=4, route_mode="air"),
        ]
        result = optimize_shipment("S1", [shipment], routes)
        self.assertIn(
            result["recommendation"]["route_mode"], {"air", "ocean"}
        )
        rejected = {route["route_id"]: route for route in result["rejected_routes"]}
        self.assertIn("ocean", " ".join(rejected["ROAD"]["rejection_reasons"]))
        self.assertIn("ocean", " ".join(rejected["RAIL"]["rejection_reasons"]))
        self.assertTrue(
            all(
                any(
                    "geographic" in reason
                    for reason in rejected[route_id]["rejection_reasons"]
                )
                for route_id in ("ROAD", "RAIL")
            )
        )

    def test_connected_land_lane_keeps_road_and_rail_candidates(self) -> None:
        shipment = make_shipment(
            origin="Los Angeles, US",
            destination="New York, US",
        )
        routes = [
            make_route("ROAD", cost=100, time=3, route_mode="road"),
            make_route("RAIL", cost=150, time=4, route_mode="rail"),
        ]
        result = optimize_shipment("S1", [shipment], routes)
        self.assertEqual(len(result["ranked_routes"]), 2)
        self.assertEqual(result["rejected_routes"], [])

    def test_geographically_invalid_candidates_cannot_be_recommended(self) -> None:
        shipment = make_shipment(origin="Tokyo, JP", destination="Mumbai, IN")
        routes = [
            make_route("ROAD", cost=1, time=1, route_mode="road"),
            make_route("RAIL", cost=2, time=2, route_mode="rail"),
        ]
        result = optimize_shipment("S1", [shipment], routes)
        self.assertEqual(result["status"], "no_feasible_route")
        self.assertIsNone(result["recommendation"])
        self.assertTrue(
            all(
                any("geographic" in reason for reason in route["rejection_reasons"])
                for route in result["rejected_routes"]
            )
        )

    def test_real_dataset_routes_are_geographically_rechecked(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        data_dir = project_root / "data"
        from backend.app.services.route_optimizer import load_dataset

        shipments, routes = load_dataset(data_dir)
        for shipment in shipments:
            result = optimize_shipment(shipment["shipment_id"], shipments, routes)
            recommended = result["recommendation"]
            if recommended:
                self.assertNotIn(
                    recommended["route_mode"],
                    {
                        route["route_mode"]
                        for route in result["rejected_routes"]
                        if any("geographic" in reason for reason in route["rejection_reasons"])
                    },
                )
            for rejected in result["rejected_routes"]:
                self.assertTrue(rejected["rejection_reasons"])


if __name__ == "__main__":
    unittest.main()
