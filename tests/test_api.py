from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.main import ROUTES, SHIPMENTS


class RouteWiseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["shipment_count"], 30)
        self.assertEqual(response.json()["route_count"], len(ROUTES))

    def test_metadata_has_measured_summary(self) -> None:
        response = self.client.get("/api/v1/metadata")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["synthetic_data"])
        self.assertEqual(payload["feasible_route_count"], 24)
        self.assertEqual(payload["shipments_without_feasible_routes"], 10)
        self.assertEqual(payload["evaluation"]["results"]["reliability_oriented"]["constraint_violations"], 0)

    def test_shipments_search_filter_and_pagination(self) -> None:
        self.assertEqual(len(self.client.get("/api/v1/shipments?limit=4").json()), 4)
        self.assertEqual(len(self.client.get("/api/v1/shipments?search=hamburg").json()) > 0, True)
        no_feasible = self.client.get("/api/v1/shipments?status=no_feasible_route")
        self.assertEqual(no_feasible.status_code, 200)
        self.assertEqual(len(no_feasible.json()), 10)

    def test_shipment_detail_and_route_options(self) -> None:
        detail = self.client.get("/api/v1/shipments/S003")
        self.assertEqual(detail.status_code, 200)
        expected_route_count = sum(route["shipment_id"] == "S003" for route in ROUTES)
        self.assertEqual(detail.json()["candidate_route_count"], expected_route_count)
        routes = self.client.get("/api/v1/shipments/S003/routes")
        self.assertEqual(routes.status_code, 200)
        self.assertEqual(len(routes.json()["routes"]), expected_route_count)
        self.assertTrue(any(row["is_feasible"] for row in routes.json()["routes"]))

    def test_unknown_shipment_returns_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/shipments/S999").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/shipments/S999/routes").status_code, 404)
        response = self.client.post("/api/v1/optimize", json={"shipment_id": "S999"})
        self.assertEqual(response.status_code, 404)

    @staticmethod
    def _new_shipment_payload(**overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "origin": "Hamburg, DE",
            "destination": "Singapore",
            "cargo_type": "electronics",
            "weight_kg": 1200,
            "max_cost_usd": 25000,
            "max_transit_days": 30,
            "max_delay_probability": 0.8,
            "max_congestion_risk": 0.8,
            "max_geopolitical_risk": 0.8,
        }
        payload.update(overrides)
        return payload

    def test_create_new_shipment_generates_reproducible_routes_and_uses_optimizer(self) -> None:
        before_shipments = [dict(row) for row in SHIPMENTS]
        before_routes = [dict(row) for row in ROUTES]
        payload = self._new_shipment_payload()
        first = self.client.post("/api/v1/shipments/optimize-new", json=payload)
        second = self.client.post("/api/v1/shipments/optimize-new", json=payload)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        result = first.json()
        self.assertEqual(result, second.json())
        self.assertEqual(result["candidate_route_source"], "synthetic_estimates")
        self.assertTrue(result["synthetic_estimates"])
        self.assertEqual(result["persistence"], "request_only")
        self.assertEqual(len(result["optimization"]["ranked_routes"]) + len(result["optimization"]["rejected_routes"]), 4)
        self.assertEqual(result["optimization"]["status"], "recommended")
        self.assertEqual(SHIPMENTS, before_shipments)
        self.assertEqual(ROUTES, before_routes)

    def test_tokyo_mumbai_new_shipment_generates_only_geographically_valid_modes(self) -> None:
        payload = self._new_shipment_payload(
            origin="Tokyo, Japan",
            destination="Mumbai, India",
            max_cost_usd=2_000_000,
            max_transit_days=2_000,
            max_delay_probability=1,
            max_congestion_risk=1,
            max_geopolitical_risk=1,
        )
        response = self.client.post("/api/v1/shipments/optimize-new", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        candidates = (
            body["optimization"]["ranked_routes"]
            + body["optimization"]["rejected_routes"]
        )
        self.assertEqual({route["route_mode"] for route in candidates}, {"air", "ocean"})
        self.assertIn(
            body["optimization"]["recommendation"]["route_mode"], {"air", "ocean"}
        )

    def test_user_supplied_impossible_tokyo_mumbai_land_routes_are_rejected(self) -> None:
        payload = self._new_shipment_payload(
            origin="Tokyo, Japan",
            destination="Mumbai, India",
            max_cost_usd=1_000_000,
            max_transit_days=100,
            max_delay_probability=1,
            max_congestion_risk=1,
            max_geopolitical_risk=1,
            candidate_routes=[
                {
                    "route_mode": mode,
                    "cost_usd": 1,
                    "transit_time_days": 1,
                    "delay_probability": 0,
                    "congestion_risk": 0,
                    "geopolitical_risk": 0,
                }
                for mode in ("road", "rail")
            ],
        )
        response = self.client.post("/api/v1/shipments/optimize-new", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["optimization"]
        self.assertEqual(result["status"], "no_feasible_route")
        self.assertIsNone(result["recommendation"])
        self.assertTrue(
            all(
                any("geographic" in reason for reason in route["rejection_reasons"])
                for route in result["rejected_routes"]
            )
        )

    def test_hamburg_singapore_case_preserves_congestion_limit_and_actual_route_metrics(self) -> None:
        payload = self._new_shipment_payload(
            origin="Hamburg, Germany",
            destination="Singapore",
            cargo_type="electronics",
            weight_kg=500,
            max_cost_usd=50000,
            max_transit_days=30,
            max_delay_probability=0.5,
            max_congestion_risk=0.0,
            max_geopolitical_risk=0.5,
        )
        zero_limit = self.client.post("/api/v1/shipments/optimize-new", json=payload)
        self.assertEqual(zero_limit.status_code, 200, zero_limit.text)
        zero_result = zero_limit.json()
        self.assertEqual(zero_result["shipment"]["shipment_id"], "NEW-E8BB77910C")
        self.assertEqual(zero_result["shipment"]["max_congestion_risk"], 0.0)
        self.assertEqual(zero_result["optimization"]["constraints"]["max_congestion_risk"], 0.0)
        self.assertEqual(zero_result["optimization"]["status"], "no_feasible_route")
        zero_routes = zero_result["optimization"]["rejected_routes"]
        self.assertEqual(len(zero_routes), 4)
        self.assertTrue(all(route["congestion_risk"] > 0 for route in zero_routes))
        self.assertTrue(all(
            any("congestion_risk" in reason for reason in route["rejection_reasons"])
            for route in zero_routes
        ))

        payload["max_delay_probability"] = 0.5
        payload["max_congestion_risk"] = 0.6
        payload["max_geopolitical_risk"] = 0.5
        intended_limit = self.client.post("/api/v1/shipments/optimize-new", json=payload)
        self.assertEqual(intended_limit.status_code, 200, intended_limit.text)
        result = intended_limit.json()
        self.assertEqual(result["shipment"]["max_congestion_risk"], 0.6)
        self.assertEqual(result["optimization"]["constraints"]["max_congestion_risk"], 0.6)
        self.assertEqual(result["optimization"]["status"], "recommended")
        routes = result["optimization"]["ranked_routes"] + result["optimization"]["rejected_routes"]
        self.assertEqual(len(routes), 4)
        self.assertTrue(all(0 < route["congestion_risk"] < 0.6 for route in routes))
        self.assertEqual(len(result["optimization"]["ranked_routes"]), 4)
        self.assertEqual(result["optimization"]["rejected_routes"], [])
        self.assertTrue(all(route["delay_probability"] <= 0.5 for route in routes))
        self.assertTrue(all(route["geopolitical_risk"] <= 0.5 for route in routes))

    def test_create_new_shipment_rejects_invalid_inputs(self) -> None:
        for invalid in (
            self._new_shipment_payload(origin="  "),
            self._new_shipment_payload(destination="Hamburg, DE"),
            self._new_shipment_payload(weight_kg=0),
            self._new_shipment_payload(max_cost_usd=-1),
            self._new_shipment_payload(max_delay_probability=1.1),
            self._new_shipment_payload(weights={"cost": 0.2, "time": 0.2, "risk": 0.2}),
        ):
            response = self.client.post("/api/v1/shipments/optimize-new", json=invalid)
            self.assertEqual(response.status_code, 422, response.text)

    def test_create_new_shipment_supports_user_routes_and_no_feasible_result(self) -> None:
        payload = self._new_shipment_payload(
            max_delay_probability=0,
            max_congestion_risk=0,
            max_geopolitical_risk=0,
            candidate_routes=[
                {
                    "route_mode": "rail",
                    "cost_usd": 5000,
                    "transit_time_days": 10,
                    "delay_probability": 0.1,
                    "congestion_risk": 0.1,
                    "geopolitical_risk": 0.1,
                },
                {
                    "route_mode": "air",
                    "cost_usd": 15000,
                    "transit_time_days": 4,
                    "delay_probability": 0.2,
                    "congestion_risk": 0.2,
                    "geopolitical_risk": 0.2,
                },
            ],
        )
        result = self.client.post("/api/v1/shipments/optimize-new", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body["candidate_route_source"], "user_supplied")
        self.assertFalse(body["synthetic_estimates"])
        self.assertEqual(body["optimization"]["status"], "no_feasible_route")
        self.assertIsNone(body["optimization"]["recommendation"])
        self.assertEqual(len(body["optimization"]["rejected_routes"]), 2)
        self.assertTrue(all(route["rejection_reasons"] for route in body["optimization"]["rejected_routes"]))

    def test_optimize_profiles_custom_weights_and_overrides(self) -> None:
        result = self.client.post(
            "/api/v1/optimize",
            json={
                "shipment_id": "S003",
                "profile": "balanced",
                "weights": {"cost": 0.5, "time": 0.3, "risk": 0.2},
            },
        )
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body["status"], "recommended")
        self.assertEqual(body["profile"], "custom")
        self.assertAlmostEqual(
            sum(body["recommendation"]["weighted_contributions"].values()),
            body["recommendation"]["total_penalty"],
            places=6,
        )
        override = self.client.post(
            "/api/v1/optimize",
            json={
                "shipment_id": "S003",
                "constraint_overrides": {"max_cost_usd": 1},
            },
        )
        self.assertEqual(override.status_code, 200)
        self.assertEqual(override.json()["status"], "no_feasible_route")

    def test_invalid_weights_and_override_rejected(self) -> None:
        bad_weights = self.client.post(
            "/api/v1/optimize",
            json={
                "shipment_id": "S003",
                "weights": {"cost": 0.1, "time": 0.1, "risk": 0.1},
            },
        )
        self.assertEqual(bad_weights.status_code, 422)
        bad_override = self.client.post(
            "/api/v1/optimize",
            json={
                "shipment_id": "S001",
                "constraint_overrides": {"max_geopolitical_risk": 2},
            },
        )
        self.assertEqual(bad_override.status_code, 422)

    def test_no_feasible_route_is_explicit(self) -> None:
        response = self.client.post(
            "/api/v1/optimize",
            json={"shipment_id": "S005"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "no_feasible_route")
        self.assertIsNone(response.json()["recommendation"])
        self.assertEqual(
            len(response.json()["rejected_routes"]),
            sum(route["shipment_id"] == "S005" for route in ROUTES),
        )

    def test_sensitivity_analysis_returns_computed_recommendations(self) -> None:
        response = self.client.post(
            "/api/v1/sensitivity",
            json={
                "shipment_id": "S001",
                "weight_sets": [
                    {"cost": 0.8, "time": 0.1, "risk": 0.1},
                    {"cost": 0.1, "time": 0.8, "risk": 0.1},
                    {"cost": 0.1, "time": 0.1, "risk": 0.8},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload["points"]), 3)
        self.assertGreaterEqual(payload["recommendation_stability"], 0)
        self.assertIn("route_changes_between_adjacent_points", payload)

    def test_openapi_documentation_is_available(self) -> None:
        schema = self.client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        paths = schema.json()["paths"]
        for endpoint in (
            "/api/v1/health",
            "/api/v1/metadata",
            "/api/v1/shipments",
            "/api/v1/shipments/{shipment_id}",
            "/api/v1/shipments/{shipment_id}/routes",
            "/api/v1/shipments/optimize-new",
            "/api/v1/optimize",
            "/api/v1/analyst/explanation",
            "/api/v1/sensitivity",
            "/api/v1/simulate-disruption",
        ):
            self.assertIn(endpoint, paths)

    def test_disruption_simulation_returns_baseline_and_hypothetical_scenarios(self) -> None:
        shipment_routes = [
            route for route in ROUTES if route["shipment_id"] == "S003"
        ]
        selected_route = shipment_routes[0]
        response = self.client.post(
            "/api/v1/simulate-disruption",
            json={
                "shipment_id": "S003",
                "scenarios": [
                    {
                        "name": "mode closure",
                        "cost_increase_pct": 0.25,
                        "route_modes": [selected_route["route_mode"]],
                    },
                    {
                        "name": "target delay",
                        "delay_probability_increase": 0.2,
                        "route_ids": [selected_route["route_id"]],
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result["hypothetical"])
        expected_candidates = len(shipment_routes)
        self.assertEqual(result["baseline"]["candidate_count"], expected_candidates)
        self.assertEqual(len(result["scenarios"]), 2)
        self.assertIn("affected_route_ids", result["scenarios"][0]["parameters"])
        self.assertEqual(len(result["scenarios"][0]["routes"]), expected_candidates)
        self.assertIn("feasible_candidate_percentage", result["scenarios"][0]["comparison"])

    def test_disruption_simulation_applies_constraint_overrides(self) -> None:
        response = self.client.post(
            "/api/v1/simulate-disruption",
            json={
                "shipment_id": "S001",
                "constraint_overrides": {"max_cost_usd": 1},
                "scenarios": [{"name": "no option", "cost_increase_pct": 0.1}],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["baseline"]["status"], "no_feasible_route")
        self.assertEqual(result["scenarios"][0]["status"], "no_feasible_route")

    def test_disruption_validation_errors_are_explicit(self) -> None:
        invalid_severity = self.client.post(
            "/api/v1/simulate-disruption",
            json={
                "shipment_id": "S001",
                "scenarios": [
                    {"name": "too much", "delay_probability_increase": 1.01}
                ],
            },
        )
        self.assertEqual(invalid_severity.status_code, 422)

        unknown_route = self.client.post(
            "/api/v1/simulate-disruption",
            json={
                "shipment_id": "S001",
                "scenarios": [{"name": "unknown", "route_ids": ["R9999"]}],
            },
        )
        self.assertEqual(unknown_route.status_code, 422)

        unknown_shipment = self.client.post(
            "/api/v1/simulate-disruption",
            json={"shipment_id": "S999", "scenarios": [{"name": "baseline"}]},
        )
        self.assertEqual(unknown_shipment.status_code, 404)

    def test_cors_allows_local_frontend(self) -> None:
        response = self.client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

    def test_analyst_endpoint_uses_optimizer_and_falls_back_without_key(self) -> None:
        from unittest.mock import patch

        with patch.dict("os.environ", {"GROQ_API_KEY": ""}, clear=False):
            response = self.client.post(
                "/api/v1/analyst/explanation",
                json={"shipment_id": "S003", "profile": "balanced"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["provider_status"], "unavailable")
        self.assertEqual(payload["source"], "deterministic")
        self.assertEqual(payload["computed_facts"]["shipment_id"], "S003")
        expected = self.client.post(
            "/api/v1/optimize",
            json={"shipment_id": "S003", "profile": "balanced"},
        ).json()["recommendation"]
        self.assertEqual(payload["computed_facts"]["selected_route_id"], expected["route_id"])
        self.assertIsNotNone(payload["computed_facts"]["cost_usd"])

    def test_analyst_endpoint_reports_no_feasible_and_unknown_shipments(self) -> None:
        no_route = self.client.post(
            "/api/v1/analyst/explanation",
            json={"shipment_id": "S005"},
        )
        self.assertEqual(no_route.status_code, 200, no_route.text)
        self.assertEqual(
            no_route.json()["computed_facts"]["status"], "no_feasible_route"
        )
        self.assertIsNone(no_route.json()["computed_facts"]["selected_route_id"])
        unknown = self.client.post(
            "/api/v1/analyst/explanation",
            json={"shipment_id": "S999"},
        )
        self.assertEqual(unknown.status_code, 404)


if __name__ == "__main__":
    unittest.main()
