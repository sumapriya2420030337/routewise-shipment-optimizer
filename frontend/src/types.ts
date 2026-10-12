export type Profile =
  | 'cost_sensitive'
  | 'balanced'
  | 'time_sensitive'
  | 'reliability_sensitive'

export type WeightSet = {
  cost: number
  time: number
  risk: number
}

export type ConstraintOverrides = {
  max_cost_usd?: number
  max_transit_days?: number
  max_delay_probability?: number
  max_congestion_risk?: number
  max_geopolitical_risk?: number
}

export type Shipment = {
  shipment_id: string
  origin: string
  destination: string
  cargo_type: string
  weight_kg: number
  distance_km: number
  max_cost_usd: number
  max_transit_days: number
  max_delay_probability: number
  max_congestion_risk: number
  max_geopolitical_risk: number
  scenario_class: 'feasible' | 'infeasible'
  candidate_route_count: number
  computed_status: 'feasible' | 'no_feasible_route'
}

export type BaselineSummary = {
  count: number
  feasibility_rate: number
  constraint_violations: number
  average_cost_usd: number
  average_transit_days: number
  average_risk_penalty: number
  average_total_penalty: number
}

export type Evaluation = {
  profile: string
  shipment_count: number
  shipments_with_feasible_routes: number
  shipments_without_feasible_routes: number
  feasibility_label_mismatch_warnings: number
  results: Record<string, BaselineSummary>
  profile_sensitivity: Record<string, Record<string, number>>
  pareto_frontier: {
    eligible_route_count: number
    non_dominated_route_count: number
    average_frontier_size_per_feasible_shipment: number
  }
  interpretation: string
}

export type Metadata = {
  synthetic_data: boolean
  shipment_count: number
  route_count: number
  feasible_route_count: number
  infeasible_route_count: number
  shipments_with_feasible_routes: number
  shipments_without_feasible_routes: number
  route_modes: Record<string, number>
  evaluation: Evaluation
}

export type HealthResponse = {
  status: string
  dataset_status: string
  shipment_count: number
  route_count: number
}

export type RouteCandidate = {
  route_id: string
  shipment_id: string
  route_mode: string
  cost_usd: number
  total_cost_usd?: number
  transit_time_days: number
  delay_probability: number
  congestion_risk: number
  geopolitical_risk: number
  stored_is_feasible: boolean
  is_feasible: boolean
  feasibility_status: 'feasible' | 'infeasible'
  rank?: number | null
  total_penalty?: number | null
  risk_components?: Record<string, number>
  risk_penalty?: number
  normalized_scores?: Record<string, number>
  weighted_contributions?: Record<string, number>
  rejection_reasons?: string[]
  competing_routes_ranked_lower?: Array<{
    route_id: string
    rank: number
    reason: string
  }>
  explanation?: string
}

export type OptimizeResponse = {
  shipment_id: string
  status: 'recommended' | 'no_feasible_route'
  profile: string
  weights: WeightSet
  constraints: ConstraintOverrides
  risk_model: {
    coefficients: Record<string, number>
    assumption: string
  }
  normalization: string
  warnings: string[]
  recommendation: RouteCandidate | null
  ranked_routes: RouteCandidate[]
  rejected_routes: RouteCandidate[]
  explanation: string
}

export type SensitivityResponse = {
  shipment_id: string
  points: Array<{
    weights: WeightSet
    status: 'recommended' | 'no_feasible_route'
    selected_route_id: string | null
    total_penalty: number | null
  }>
  recommendation_counts: Record<string, number>
  recommendation_stability: number
  route_changes_between_adjacent_points: number
  explanation: string
}

export type OptimizeRequest = {
  shipment_id: string
  profile: Profile
  weights: WeightSet
  constraint_overrides: ConstraintOverrides
}

export type NewCandidateRouteInput = {
  route_mode: 'air' | 'ocean' | 'rail' | 'road'
  cost_usd: number
  transit_time_days: number
  delay_probability: number
  congestion_risk: number
  geopolitical_risk: number
}

export type NewShipmentRequest = {
  origin: string
  destination: string
  cargo_type: string
  weight_kg: number
  max_cost_usd: number
  max_transit_days: number
  max_delay_probability: number
  max_congestion_risk: number
  max_geopolitical_risk: number
  profile: Profile
  weights: WeightSet
  constraint_overrides: ConstraintOverrides
  candidate_routes?: NewCandidateRouteInput[]
}

export type NewShipmentOptimization = {
  shipment: Omit<Shipment, 'distance_km' | 'candidate_route_count' | 'scenario_class' | 'computed_status'> & {
    estimated_distance_km: number
  }
  candidate_route_source: 'synthetic_estimates' | 'user_supplied'
  synthetic_estimates: boolean
  persistence: 'request_only'
  optimization: OptimizeResponse
}

export type AnalystAlternativeFact = {
  route_id: string
  route_mode: string
  cost_usd: number
  transit_time_days: number
  risk_penalty: number
  total_penalty: number
}

export type AnalystFacts = {
  shipment_id: string
  status: 'recommended' | 'no_feasible_route'
  selected_route_id: string | null
  selected_route_mode: string | null
  cost_usd: number | null
  transit_time_days: number | null
  delay_probability: number | null
  congestion_risk: number | null
  geopolitical_risk: number | null
  risk_penalty: number | null
  total_penalty: number | null
  weighted_contributions: Record<string, number>
  weights: WeightSet | null
  constraints: Record<string, number>
  cheapest_feasible: AnalystAlternativeFact | null
  fastest_feasible: AnalystAlternativeFact | null
  rejected_route_count: number
}

export type AnalystExplanation = {
  shipment_id: string
  provider_status: 'generated' | 'unavailable' | 'error' | 'not_applicable'
  source: 'groq' | 'deterministic'
  model: string | null
  narrative: {
    summary: string
    tradeoffs: string[]
    constraint_notes: string[]
    uncertainties: string[]
  }
  computed_facts: AnalystFacts
  warning: string | null
}

export type DisruptionScenarioInput = {
  name: string
  delay_probability_increase: number
  congestion_risk_increase: number
  geopolitical_risk_increase: number
  transit_time_increase_pct: number
  cost_increase_pct: number
  route_modes: string[]
  route_ids: string[]
}

export type SimulationRoute = {
  route_id: string
  route_mode: string
  baseline_metrics: {
    cost_usd: number
    transit_time_days: number
    delay_probability: number
    congestion_risk: number
    geopolitical_risk: number
  }
  disrupted_metrics: {
    cost_usd: number
    transit_time_days: number
    delay_probability: number
    congestion_risk: number
    geopolitical_risk: number
  }
  baseline_feasible: boolean
  disrupted_feasible: boolean
  baseline_rejection_reasons: string[]
  disrupted_rejection_reasons: string[]
  baseline_rank: number | null
  disrupted_rank: number | null
  baseline_penalty: number | null
  disrupted_penalty: number | null
  changed_metrics: Record<string, { baseline: number; disrupted: number }>
}

export type DisruptionComparison = {
  original_recommendation_route_id: string | null
  disrupted_recommendation_route_id: string | null
  original_recommendation_remains_feasible: boolean
  recommendation_changed: boolean
  feasible_candidate_count: number
  feasible_candidate_percentage: number
  baseline_feasible_candidate_count: number
  feasible_candidate_change: number
  fallback_available: boolean
  recommended_cost_change_usd: number | null
  recommended_transit_time_change_days: number | null
  recommended_risk_penalty_change: number | null
}

export type DisruptionScenarioResult = {
  name: string
  parameters: Record<string, unknown>
  status: 'recommended' | 'no_feasible_route'
  recommendation: RouteCandidate | null
  ranked_routes: RouteCandidate[]
  rejected_routes: RouteCandidate[]
  comparison: DisruptionComparison
  routes: SimulationRoute[]
  summary: string
}

export type DisruptionResponse = {
  shipment_id: string
  hypothetical: true
  profile: string
  weights: WeightSet
  baseline: {
    status: 'recommended' | 'no_feasible_route'
    recommendation: RouteCandidate | null
    ranked_routes: RouteCandidate[]
    rejected_routes: RouteCandidate[]
    feasible_candidate_count: number
    candidate_count: number
  }
  scenarios: DisruptionScenarioResult[]
  assumptions: string[]
}
