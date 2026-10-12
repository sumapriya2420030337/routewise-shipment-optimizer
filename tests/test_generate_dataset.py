from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.generate_dataset import (
    DEFAULT_SEED,
    MAX_ROUTES_PER_SHIPMENT,
    ROUTE_FIELDS,
    SHIPMENT_FIELDS,
    SHIPMENT_COUNT,
    generate_dataset,
    route_is_feasible,
    validate_dataset,
    write_dataset,
)


class GenerateDatasetTests(unittest.TestCase):
    def test_default_seed_is_reproducible_and_has_expected_shape(self) -> None:
        first_shipments, first_routes = generate_dataset()
        second_shipments, second_routes = generate_dataset(DEFAULT_SEED)

        self.assertEqual(first_shipments, second_shipments)
        self.assertEqual(first_routes, second_routes)
        self.assertEqual(len(first_shipments), 30)
        self.assertGreaterEqual(len(first_routes), len(first_shipments))
        self.assertLessEqual(
            len(first_routes), len(first_shipments) * MAX_ROUTES_PER_SHIPMENT
        )
        self.assertEqual(
            {row["scenario_class"] for row in first_shipments},
            {"feasible", "infeasible"},
        )
        validate_dataset(first_shipments, first_routes)

    def test_generation_preserves_scenario_classes_when_a_lane_has_few_modes(self) -> None:
        shipments, routes = generate_dataset()
        routes_by_shipment: dict[str, list[dict[str, object]]] = {}
        for route in routes:
            routes_by_shipment.setdefault(str(route["shipment_id"]), []).append(route)

        for shipment in shipments:
            candidate_routes = routes_by_shipment[str(shipment["shipment_id"])]
            feasible = [
                route for route in candidate_routes if route["is_feasible"] == "true"
            ]
            if shipment["scenario_class"] == "feasible":
                self.assertGreaterEqual(len(feasible), 1)
            else:
                self.assertEqual(feasible, [])

    def test_validation_rejects_duplicate_ids(self) -> None:
        shipments, routes = generate_dataset()
        routes[1]["route_id"] = routes[0]["route_id"]

        with self.assertRaisesRegex(ValueError, "Route IDs"):
            validate_dataset(shipments, routes)

    def test_validation_rejects_unknown_shipment_reference(self) -> None:
        shipments, routes = generate_dataset()
        routes[0]["shipment_id"] = "S999"

        with self.assertRaisesRegex(ValueError, "unknown shipment"):
            validate_dataset(shipments, routes)

    def test_validation_rejects_out_of_range_probability(self) -> None:
        shipments, routes = generate_dataset()
        routes[0]["delay_probability"] = 1.01

        with self.assertRaisesRegex(ValueError, "delay_probability"):
            validate_dataset(shipments, routes)

    def test_validation_accepts_zero_probability(self) -> None:
        shipments, routes = generate_dataset()
        shipment_by_id = {row["shipment_id"]: row for row in shipments}
        route = next(
            row
            for row in routes
            if shipment_by_id[row["shipment_id"]]["scenario_class"] == "feasible"
            and row["is_feasible"] == "true"
        )
        route["delay_probability"] = 0.0
        route["is_feasible"] = str(route_is_feasible(shipment_by_id[route["shipment_id"]], route)).lower()

        validate_dataset(shipments, routes)

    def test_validation_rejects_wrong_route_count(self) -> None:
        shipments, routes = generate_dataset()
        missing_shipment_id = shipments[0]["shipment_id"]
        routes = [
            row for row in routes if row["shipment_id"] != missing_shipment_id
        ]

        with self.assertRaisesRegex(ValueError, "must have 1 to"):
            validate_dataset(shipments, routes)

    def test_generation_uses_only_geographically_supported_modes(self) -> None:
        shipments, routes = generate_dataset()
        shipment_by_id = {row["shipment_id"]: row for row in shipments}
        tokyo_mumbai_ids = {
            row["shipment_id"]
            for row in shipments
            if row["origin"].startswith("Tokyo,")
            and row["destination"].startswith("Mumbai,")
        }
        # The deterministic sample may not contain this direction; use the
        # shared check directly to prove the unsupported modes are rejected.
        from backend.app.services.geography import transport_mode_rejection_reason

        self.assertIsNotNone(
            transport_mode_rejection_reason("Tokyo, JP", "Mumbai, IN", "road")
        )
        self.assertIsNotNone(
            transport_mode_rejection_reason("Tokyo, JP", "Mumbai, IN", "rail")
        )
        self.assertFalse(
            any(
                route["shipment_id"] in tokyo_mumbai_ids
                and route["route_mode"] in {"road", "rail"}
                for route in routes
            )
        )
        self.assertEqual(len(shipment_by_id), len(shipments))

    def test_writer_outputs_csv_headers_and_records(self) -> None:
        shipments, routes = generate_dataset()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            write_dataset(shipments, routes, output_dir)

            with (output_dir / "shipments.csv").open(encoding="utf-8", newline="") as file:
                shipment_rows = list(csv.DictReader(file))
                self.assertEqual(list(shipment_rows[0]), SHIPMENT_FIELDS)
                self.assertEqual(len(shipment_rows), SHIPMENT_COUNT)
            with (output_dir / "routes.csv").open(encoding="utf-8", newline="") as file:
                route_rows = list(csv.DictReader(file))
                self.assertEqual(list(route_rows[0]), ROUTE_FIELDS)
                self.assertEqual(len(route_rows), len(routes))


if __name__ == "__main__":
    unittest.main()
