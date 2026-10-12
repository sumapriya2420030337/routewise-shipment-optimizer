from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from backend.app.main import ROUTES, SHIPMENTS
from backend.app.services.analyst import explain_optimization
from backend.app.services.route_optimizer import optimize_shipment


def _result(shipment_id: str = "S003") -> dict[str, object]:
    return optimize_shipment(shipment_id, SHIPMENTS, ROUTES)


class AnalystExplanationTests(unittest.TestCase):
    def test_missing_key_returns_deterministic_explanation_and_computed_facts(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False):
            response = asyncio.run(explain_optimization(_result()))

        payload = response.model_dump()
        self.assertEqual(payload["provider_status"], "unavailable")
        self.assertEqual(payload["source"], "deterministic")
        self.assertEqual(payload["computed_facts"]["selected_route_id"], _result()["recommendation"]["route_id"])
        self.assertEqual(payload["computed_facts"]["cost_usd"], _result()["recommendation"]["cost_usd"])
        self.assertIn("GROQ_API_KEY", payload["warning"])

    def test_no_feasible_route_uses_deterministic_rejection_summary(self) -> None:
        response = asyncio.run(explain_optimization(_result("S005")))

        self.assertEqual(response.provider_status, "not_applicable")
        self.assertEqual(response.computed_facts.status, "no_feasible_route")
        self.assertIsNone(response.computed_facts.selected_route_id)
        self.assertEqual(response.computed_facts.rejected_route_count, 2)
        self.assertIn("No candidate satisfies", response.narrative.summary)

    def test_groq_response_is_validated_and_only_adds_commentary(self) -> None:
        generated = (
            '{"summary":"The selected option balances the supplied priorities.",'
            '"tradeoffs":["The cheapest option gives up some speed or risk balance."],'
            '"constraint_notes":["Only eligible alternatives were ranked."],'
            '"uncertainties":["All supplied values are synthetic assumptions."]}'
        )
        with (
            patch.dict(
                os.environ,
                {
                    "GROQ_API_KEY": "test-key-never-sent",
                    "GROQ_MODEL": "test/model",
                    "GROQ_PROVIDER": "groq",
                },
                clear=False,
            ),
            patch("backend.app.services.analyst._request_groq", return_value=generated),
        ):
            response = asyncio.run(explain_optimization(_result()))

        self.assertEqual(response.provider_status, "generated")
        self.assertEqual(response.source, "groq")
        self.assertEqual(response.model, "test/model")
        self.assertEqual(response.narrative.summary, "The selected option balances the supplied priorities.")
        self.assertEqual(response.computed_facts.selected_route_id, _result()["recommendation"]["route_id"])

    def test_malformed_or_numeric_ai_claim_uses_deterministic_fallback(self) -> None:
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False),
            patch(
                "backend.app.services.analyst._request_groq",
                return_value=(
                    '{"summary":"Route R0001 is best.",'
                    '"tradeoffs":["There are no trade-offs."],'
                    '"constraint_notes":["Limits were enforced."],'
                    '"uncertainties":["Values are synthetic."]}'
                ),
            ),
        ):
            response = asyncio.run(explain_optimization(_result()))

        self.assertEqual(response.provider_status, "error")
        self.assertEqual(response.source, "deterministic")
        self.assertIn("deterministic explanation", response.warning)


if __name__ == "__main__":
    unittest.main()
