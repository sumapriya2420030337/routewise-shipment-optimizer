"""Typed request and response contracts for the RouteWise API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProfileName = Literal[
    "cost_sensitive",
    "balanced",
    "time_sensitive",
    "reliability_sensitive",
]
RouteMode = Literal["air", "ocean", "rail", "road"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Weights(StrictModel):
    cost: float = Field(ge=0, le=1)
    time: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> Weights:
        total = self.cost + self.time + self.risk
        if abs(total - 1.0) > 1e-9:
            raise ValueError("cost, time, and risk weights must sum to 1 within 1e-9")
        return self


class ConstraintOverrides(StrictModel):
    max_cost_usd: float | None = Field(default=None, gt=0, le=1_000_000_000)
    max_transit_days: float | None = Field(default=None, gt=0, le=100_000)
    max_delay_probability: float | None = Field(default=None, ge=0, le=1)
    max_congestion_risk: float | None = Field(default=None, ge=0, le=1)
    max_geopolitical_risk: float | None = Field(default=None, ge=0, le=1)

    def as_overrides(self) -> dict[str, float]:
        return {
            name: value
            for name, value in self.model_dump().items()
            if value is not None
        }


class OptimizeRequest(StrictModel):
    shipment_id: str = Field(min_length=1, max_length=40)
    profile: ProfileName = "balanced"
    weights: Weights | None = None
    constraint_overrides: ConstraintOverrides | None = None


class NewCandidateRoute(StrictModel):
    route_mode: RouteMode
    cost_usd: float = Field(gt=0, le=1_000_000_000)
    transit_time_days: float = Field(gt=0, le=100_000)
    delay_probability: float = Field(ge=0, le=1)
    congestion_risk: float = Field(ge=0, le=1)
    geopolitical_risk: float = Field(ge=0, le=1)


class NewShipmentRequest(StrictModel):
    origin: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    cargo_type: str = Field(min_length=1, max_length=60)
    weight_kg: float = Field(gt=0, le=1_000_000_000)
    max_cost_usd: float = Field(gt=0, le=1_000_000_000)
    max_transit_days: float = Field(gt=0, le=100_000)
    max_delay_probability: float = Field(ge=0, le=1)
    max_congestion_risk: float = Field(ge=0, le=1)
    max_geopolitical_risk: float = Field(ge=0, le=1)
    profile: ProfileName = "balanced"
    weights: Weights | None = None
    constraint_overrides: ConstraintOverrides | None = None
    candidate_routes: list[NewCandidateRoute] | None = Field(default=None, min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_lane(self) -> NewShipmentRequest:
        self.origin = self.origin.strip()
        self.destination = self.destination.strip()
        self.cargo_type = self.cargo_type.strip()
        if not self.origin or not self.destination or not self.cargo_type:
            raise ValueError("origin, destination, and cargo_type must not be blank")
        if self.origin.casefold() == self.destination.casefold():
            raise ValueError("origin and destination must be different")
        return self


class NewShipmentDetails(StrictModel):
    shipment_id: str
    origin: str
    destination: str
    cargo_type: str
    weight_kg: float
    max_cost_usd: float
    max_transit_days: float
    max_delay_probability: float
    max_congestion_risk: float
    max_geopolitical_risk: float
    estimated_distance_km: float


class SensitivityRequest(StrictModel):
    shipment_id: str = Field(min_length=1, max_length=40)
    weight_sets: list[Weights] = Field(min_length=2, max_length=30)
    constraint_overrides: ConstraintOverrides | None = None


class DisruptionScenario(StrictModel):
    name: str = Field(min_length=1, max_length=60, pattern=r".*\S.*")
    delay_probability_increase: float = Field(default=0.0, ge=0, le=1)
    congestion_risk_increase: float = Field(default=0.0, ge=0, le=1)
    geopolitical_risk_increase: float = Field(default=0.0, ge=0, le=1)
    transit_time_increase_pct: float = Field(default=0.0, ge=0, le=5)
    cost_increase_pct: float = Field(default=0.0, ge=0, le=5)
    route_modes: list[RouteMode] = Field(default_factory=list, max_length=4)
    route_ids: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def unique_route_selectors(self) -> DisruptionScenario:
        if len(set(self.route_modes)) != len(self.route_modes):
            raise ValueError("route_modes must not contain duplicates")
        if len(set(self.route_ids)) != len(self.route_ids):
            raise ValueError("route_ids must not contain duplicates")
        if any(not route_id.strip() for route_id in self.route_ids):
            raise ValueError("route_ids must be non-empty")
        return self


class DisruptionRequest(StrictModel):
    shipment_id: str = Field(min_length=1, max_length=40)
    profile: ProfileName = "balanced"
    weights: Weights | None = None
    constraint_overrides: ConstraintOverrides | None = None
    scenarios: list[DisruptionScenario] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def unique_scenario_names(self) -> DisruptionRequest:
        names = [scenario.name.casefold() for scenario in self.scenarios]
        if len(set(names)) != len(names):
            raise ValueError("scenario names must be unique")
        return self


class Shipment(StrictModel):
    shipment_id: str
    origin: str
    destination: str
    cargo_type: str
    weight_kg: float
    distance_km: float
    max_cost_usd: float
    max_transit_days: float
    max_delay_probability: float
    max_congestion_risk: float
    max_geopolitical_risk: float
    scenario_class: Literal["feasible", "infeasible"]
    candidate_route_count: int
    computed_status: Literal["feasible", "no_feasible_route"]


class RejectionReason(StrictModel):
    route_id: str
    reasons: list[str]


class RouteScore(StrictModel):
    route_id: str
    shipment_id: str
    route_mode: str
    cost_usd: float
    total_cost_usd: float
    transit_time_days: float
    delay_probability: float
    congestion_risk: float
    geopolitical_risk: float
    stored_is_feasible: bool
    is_feasible: bool
    feasibility_status: str
    risk_components: dict[str, float]
    risk_penalty: float
    normalized_scores: dict[str, float]
    weighted_contributions: dict[str, float]
    total_penalty: float
    rank: int
    competing_routes_ranked_lower: list[dict[str, object]] = Field(default_factory=list)
    active_weights: dict[str, float]
    active_constraints: dict[str, float]
    assumptions: list[str]
    explanation: str


class RouteCandidate(StrictModel):
    route_id: str
    shipment_id: str
    route_mode: str
    cost_usd: float
    transit_time_days: float
    delay_probability: float
    congestion_risk: float
    geopolitical_risk: float
    stored_is_feasible: bool
    is_feasible: bool
    feasibility_status: str
    rank: int | None = None
    total_penalty: float | None = None
    rejection_reasons: list[str] = Field(default_factory=list)


class OptimizeResponse(StrictModel):
    shipment_id: str
    status: Literal["recommended", "no_feasible_route"]
    profile: str
    weights: dict[str, float]
    constraints: dict[str, float]
    risk_model: dict[str, object]
    normalization: str
    warnings: list[str]
    recommendation: RouteScore | None
    ranked_routes: list[RouteScore]
    rejected_routes: list[RouteCandidate]
    explanation: str


class NewShipmentOptimizationResponse(StrictModel):
    shipment: NewShipmentDetails
    candidate_route_source: Literal["synthetic_estimates", "user_supplied"]
    synthetic_estimates: bool
    persistence: Literal["request_only"]
    optimization: OptimizeResponse


class RoutesResponse(StrictModel):
    shipment_id: str
    status: Literal["recommended", "no_feasible_route"]
    routes: list[RouteCandidate]


class SensitivityPoint(StrictModel):
    weights: Weights
    status: Literal["recommended", "no_feasible_route"]
    selected_route_id: str | None
    total_penalty: float | None


class SensitivityResponse(StrictModel):
    shipment_id: str
    points: list[SensitivityPoint]
    recommendation_counts: dict[str, int]
    recommendation_stability: float
    route_changes_between_adjacent_points: int
    explanation: str


class AnalystNarrative(StrictModel):
    summary: str = Field(min_length=1, max_length=500)
    tradeoffs: list[str] = Field(min_length=1, max_length=4)
    constraint_notes: list[str] = Field(min_length=1, max_length=4)
    uncertainties: list[str] = Field(min_length=1, max_length=3)


class AnalystAlternativeFact(StrictModel):
    route_id: str
    route_mode: str
    cost_usd: float
    transit_time_days: float
    risk_penalty: float
    total_penalty: float


class AnalystFacts(StrictModel):
    shipment_id: str
    status: Literal["recommended", "no_feasible_route"]
    selected_route_id: str | None = None
    selected_route_mode: str | None = None
    cost_usd: float | None = None
    transit_time_days: float | None = None
    delay_probability: float | None = None
    congestion_risk: float | None = None
    geopolitical_risk: float | None = None
    risk_penalty: float | None = None
    total_penalty: float | None = None
    weighted_contributions: dict[str, float] = Field(default_factory=dict)
    weights: Weights | None = None
    constraints: dict[str, float] = Field(default_factory=dict)
    cheapest_feasible: AnalystAlternativeFact | None = None
    fastest_feasible: AnalystAlternativeFact | None = None
    rejected_route_count: int


class AnalystExplanationResponse(StrictModel):
    shipment_id: str
    provider_status: Literal["generated", "unavailable", "error", "not_applicable"]
    source: Literal["groq", "deterministic"]
    model: str | None = None
    narrative: AnalystNarrative
    computed_facts: AnalystFacts
    warning: str | None = None


class RouteSimulationMetrics(StrictModel):
    cost_usd: float
    transit_time_days: float
    delay_probability: float
    congestion_risk: float
    geopolitical_risk: float


class SimulatedRoute(StrictModel):
    route_id: str
    route_mode: RouteMode
    baseline_metrics: RouteSimulationMetrics
    disrupted_metrics: RouteSimulationMetrics
    baseline_feasible: bool
    disrupted_feasible: bool
    baseline_rejection_reasons: list[str]
    disrupted_rejection_reasons: list[str]
    baseline_rank: int | None
    disrupted_rank: int | None
    baseline_penalty: float | None
    disrupted_penalty: float | None
    changed_metrics: dict[str, dict[str, float]]


class DisruptionComparison(StrictModel):
    original_recommendation_route_id: str | None
    disrupted_recommendation_route_id: str | None
    original_recommendation_remains_feasible: bool
    recommendation_changed: bool
    feasible_candidate_count: int
    feasible_candidate_percentage: float
    baseline_feasible_candidate_count: int
    feasible_candidate_change: int
    fallback_available: bool
    recommended_cost_change_usd: float | None
    recommended_transit_time_change_days: float | None
    recommended_risk_penalty_change: float | None


class DisruptionBaseline(StrictModel):
    status: Literal["recommended", "no_feasible_route"]
    recommendation: RouteScore | None
    ranked_routes: list[RouteScore]
    rejected_routes: list[RouteCandidate]
    feasible_candidate_count: int
    candidate_count: int


class DisruptionScenarioResult(StrictModel):
    name: str
    parameters: dict[str, object]
    status: Literal["recommended", "no_feasible_route"]
    recommendation: RouteScore | None
    ranked_routes: list[RouteScore]
    rejected_routes: list[RouteCandidate]
    comparison: DisruptionComparison
    routes: list[SimulatedRoute]
    summary: str


class DisruptionResponse(StrictModel):
    shipment_id: str
    hypothetical: Literal[True]
    profile: str
    weights: dict[str, float]
    baseline: DisruptionBaseline
    scenarios: list[DisruptionScenarioResult]
    assumptions: list[str]


class BaselineSummary(StrictModel):
    count: int
    feasibility_rate: float
    constraint_violations: int
    average_cost_usd: float
    average_transit_days: float
    average_risk_penalty: float
    average_total_penalty: float


class Evaluation(StrictModel):
    profile: str
    shipment_count: int
    shipments_with_feasible_routes: int
    shipments_without_feasible_routes: int
    feasibility_label_mismatch_warnings: int
    results: dict[str, BaselineSummary]
    profile_sensitivity: dict[str, dict[str, int]]
    pareto_frontier: dict[str, float | int]
    interpretation: str


class Metadata(StrictModel):
    synthetic_data: bool
    shipment_count: int
    route_count: int
    feasible_route_count: int
    infeasible_route_count: int
    shipments_with_feasible_routes: int
    shipments_without_feasible_routes: int
    route_modes: dict[str, int]
    evaluation: Evaluation


class Health(StrictModel):
    status: Literal["ok"]
    dataset_status: Literal["loaded"]
    shipment_count: int
    route_count: int
