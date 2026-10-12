"""Optional Groq commentary over authoritative optimizer results."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from backend.app.schemas import (
    AnalystAlternativeFact,
    AnalystExplanationResponse,
    AnalystFacts,
    AnalystNarrative,
    Weights,
)

logger = logging.getLogger(__name__)
DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_COMPLETION_TOKENS = 500


def _alternative_fact(route: dict[str, Any]) -> AnalystAlternativeFact:
    return AnalystAlternativeFact(
        route_id=route["route_id"],
        route_mode=route["route_mode"],
        cost_usd=route["cost_usd"],
        transit_time_days=route["transit_time_days"],
        risk_penalty=route["risk_penalty"],
        total_penalty=route["total_penalty"],
    )


def _facts(result: dict[str, Any]) -> AnalystFacts:
    ranked_routes = result["ranked_routes"]
    recommendation = result["recommendation"]
    cheapest = min(ranked_routes, key=lambda route: (route["cost_usd"], route["route_id"])) if ranked_routes else None
    fastest = min(
        ranked_routes,
        key=lambda route: (route["transit_time_days"], route["route_id"]),
    ) if ranked_routes else None
    return AnalystFacts(
        shipment_id=result["shipment_id"],
        status=result["status"],
        selected_route_id=recommendation["route_id"] if recommendation else None,
        selected_route_mode=recommendation["route_mode"] if recommendation else None,
        cost_usd=recommendation["cost_usd"] if recommendation else None,
        transit_time_days=(
            recommendation["transit_time_days"] if recommendation else None
        ),
        delay_probability=(
            recommendation["delay_probability"] if recommendation else None
        ),
        congestion_risk=(
            recommendation["congestion_risk"] if recommendation else None
        ),
        geopolitical_risk=(
            recommendation["geopolitical_risk"] if recommendation else None
        ),
        risk_penalty=recommendation["risk_penalty"] if recommendation else None,
        total_penalty=recommendation["total_penalty"] if recommendation else None,
        weighted_contributions=(
            recommendation["weighted_contributions"] if recommendation else {}
        ),
        weights=Weights(**result["weights"]),
        constraints=result["constraints"],
        cheapest_feasible=_alternative_fact(cheapest) if cheapest else None,
        fastest_feasible=_alternative_fact(fastest) if fastest else None,
        rejected_route_count=len(result["rejected_routes"]),
    )


def _deterministic_narrative(facts: AnalystFacts) -> AnalystNarrative:
    if facts.status == "no_feasible_route":
        return AnalystNarrative(
            summary=(
                "No candidate satisfies every active hard constraint. "
                "The optimizer has not recommended an ineligible route."
            ),
            tradeoffs=[
                "Review the active shipment limits or candidate data before choosing a route."
            ],
            constraint_notes=[
                f"{facts.rejected_route_count} candidates were rejected by the recomputed hard constraints."
            ],
            uncertainties=[
                "Candidate costs, transit times, and risks are synthetic estimates."
            ],
        )

    selected_id = facts.selected_route_id or "the selected route"
    alternatives = []
    if facts.cheapest_feasible:
        if facts.cheapest_feasible.route_id == selected_id:
            alternatives.append("The selected route is also the cheapest feasible candidate.")
        else:
            alternatives.append(
                f"The cheapest feasible alternative is {facts.cheapest_feasible.route_id}; "
                "it may trade lower cost against the active time and risk priorities."
            )
    if facts.fastest_feasible:
        if facts.fastest_feasible.route_id == selected_id:
            alternatives.append("The selected route is also the fastest feasible candidate.")
        else:
            alternatives.append(
                f"The fastest feasible alternative is {facts.fastest_feasible.route_id}; "
                "compare its cost and risk before changing the selection."
            )
    if not alternatives:
        alternatives.append("There are no competing feasible candidates for this shipment.")
    return AnalystNarrative(
        summary=(
            f"The deterministic optimizer selected {selected_id} using the active "
            "weights after enforcing all hard constraints."
        ),
        tradeoffs=alternatives[:4],
        constraint_notes=[
            f"{facts.rejected_route_count} candidates failed at least one hard constraint."
            if facts.rejected_route_count
            else "All candidate routes passed the active hard constraints."
        ],
        uncertainties=[
            "Dataset values and risk coefficients are synthetic illustrative assumptions."
        ],
    )


def _model_context(result: dict[str, Any], facts: AnalystFacts) -> dict[str, Any]:
    return {
        "shipment_id": facts.shipment_id,
        "status": facts.status,
        "selected_route": (
            {
                "route_id": facts.selected_route_id,
                "mode": facts.selected_route_mode,
                "cost_usd": facts.cost_usd,
                "transit_time_days": facts.transit_time_days,
                "delay_probability": facts.delay_probability,
                "congestion_risk": facts.congestion_risk,
                "geopolitical_risk": facts.geopolitical_risk,
                "risk_penalty": facts.risk_penalty,
                "objective_penalty": facts.total_penalty,
                "weighted_contributions": facts.weighted_contributions,
            }
            if facts.selected_route_id
            else None
        ),
        "weights": facts.weights.model_dump() if facts.weights else {},
        "constraints": facts.constraints,
        "cheapest_feasible": (
            facts.cheapest_feasible.model_dump() if facts.cheapest_feasible else None
        ),
        "fastest_feasible": (
            facts.fastest_feasible.model_dump() if facts.fastest_feasible else None
        ),
        "rejected_candidates": [
            {
                "route_id": route["route_id"],
                "reasons": route["rejection_reasons"],
            }
            for route in result["rejected_routes"]
        ],
    }


def _narrative_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "tradeoffs": {"type": "array", "items": {"type": "string"}},
            "constraint_notes": {"type": "array", "items": {"type": "string"}},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "tradeoffs", "constraint_notes", "uncertainties"],
        "additionalProperties": False,
    }


def _request_groq(context: dict[str, Any], api_key: str, model: str) -> str:
    from groq import Groq

    client = Groq(api_key=api_key, timeout=15.0, max_retries=0)
    completion = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "routewise_analyst",
                "strict": True,
                "schema": _narrative_schema(),
            },
        },
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the RouteWise logistics analyst. Summarize only the "
                    "supplied computed result. Never rank routes, alter feasibility, "
                    "override constraints, or invent costs, risks, causes, forecasts, "
                    "or external facts. Discuss why the computed selection fits the "
                    "weights, the supplied cheapest/fastest alternatives, the stated "
                    "constraint rejections, and uncertainty. The UI separately shows "
                    "all numeric facts from the optimizer, so use no digits, numbers, "
                    "percentages, currency figures, route IDs, or new quantitative "
                    "claims in your text. Return concise valid JSON matching the schema."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, separators=(",", ":"), ensure_ascii=True),
            },
        ],
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("Groq returned an empty analyst response")
    return content


def _parse_narrative(content: str) -> AnalystNarrative:
    narrative = AnalystNarrative.model_validate_json(content)
    if any(
        re.search(r"\d", phrase)
        for phrase in [
            narrative.summary,
            *narrative.tradeoffs,
            *narrative.constraint_notes,
            *narrative.uncertainties,
        ]
    ):
        raise ValueError("Analyst narrative included unverified numeric claims")
    return narrative


async def explain_optimization(result: dict[str, Any]) -> AnalystExplanationResponse:
    facts = _facts(result)
    if facts.status == "no_feasible_route":
        return AnalystExplanationResponse(
            shipment_id=facts.shipment_id,
            provider_status="not_applicable",
            source="deterministic",
            narrative=_deterministic_narrative(facts),
            computed_facts=facts,
            warning="AI commentary is skipped when the optimizer has no feasible route.",
        )

    provider = os.getenv("GROQ_PROVIDER", "groq").strip().lower()
    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if provider != "groq" or not api_key:
        logger.info(
            "Using deterministic analyst fallback (provider=%s, api_key_configured=%s)",
            provider,
            bool(api_key),
        )
        return AnalystExplanationResponse(
            shipment_id=facts.shipment_id,
            provider_status="unavailable",
            source="deterministic",
            model=model if provider == "groq" else None,
            narrative=_deterministic_narrative(facts),
            computed_facts=facts,
            warning=(
                "Groq is not configured; showing a deterministic explanation. "
                "Set GROQ_API_KEY to enable optional AI commentary."
                if provider == "groq"
                else "The configured analyst provider is unsupported; showing a deterministic explanation."
            ),
        )

    try:
        response_text = await asyncio.to_thread(
            _request_groq, _model_context(result, facts), api_key, model
        )
        narrative = _parse_narrative(response_text)
    except Exception as exc:
        logger.warning("Groq analyst request failed (%s)", type(exc).__name__)
        return AnalystExplanationResponse(
            shipment_id=facts.shipment_id,
            provider_status="error",
            source="deterministic",
            model=model,
            narrative=_deterministic_narrative(facts),
            computed_facts=facts,
            warning="AI commentary was unavailable or invalid; showing the deterministic explanation instead.",
        )

    return AnalystExplanationResponse(
        shipment_id=facts.shipment_id,
        provider_status="generated",
        source="groq",
        model=model,
        narrative=narrative,
        computed_facts=facts,
    )
