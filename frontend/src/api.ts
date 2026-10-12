import type {
  AnalystExplanation,
  ConstraintOverrides,
  DisruptionResponse,
  DisruptionScenarioInput,
  HealthResponse,
  Metadata,
  NewShipmentOptimization,
  NewShipmentRequest,
  OptimizeRequest,
  OptimizeResponse,
  Profile,
  SensitivityResponse,
  Shipment,
  WeightSet,
} from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiConnectionError extends Error {
  constructor(message: string, cause: unknown) {
    super(message, { cause })
    this.name = 'ApiConnectionError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'Network request failed'
    throw new ApiConnectionError(`Cannot reach the RouteWise API. ${reason}`, error)
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      detail = body.detail ?? detail
    } catch {
      // Keep the HTTP status as the visible error if the server body is not JSON.
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return request('/api/v1/health')
}

export function getMetadata(): Promise<Metadata> {
  return request('/api/v1/metadata')
}

export function listShipments(search = ''): Promise<Shipment[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : ''
  return request(`/api/v1/shipments${query}`)
}

export function getShipment(shipmentId: string): Promise<Shipment> {
  return request(`/api/v1/shipments/${encodeURIComponent(shipmentId)}`)
}

export function optimizeShipment(input: OptimizeRequest): Promise<OptimizeResponse> {
  return request('/api/v1/optimize', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function optimizeNewShipment(input: NewShipmentRequest): Promise<NewShipmentOptimization> {
  return request('/api/v1/shipments/optimize-new', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function explainOptimization(input: OptimizeRequest): Promise<AnalystExplanation> {
  return request('/api/v1/analyst/explanation', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function analyzeSensitivity(
  shipmentId: string,
  weightSets: WeightSet[],
  constraintOverrides: ConstraintOverrides,
): Promise<SensitivityResponse> {
  return request('/api/v1/sensitivity', {
    method: 'POST',
    body: JSON.stringify({
      shipment_id: shipmentId,
      weight_sets: weightSets,
      constraint_overrides: constraintOverrides,
    }),
  })
}

export function simulateDisruptions(
  shipmentId: string,
  scenarios: DisruptionScenarioInput[],
  profile: Profile,
  weights: WeightSet,
  constraintOverrides: ConstraintOverrides = {},
): Promise<DisruptionResponse> {
  return request('/api/v1/simulate-disruption', {
    method: 'POST',
    body: JSON.stringify({
      shipment_id: shipmentId,
      profile,
      weights,
      constraint_overrides: constraintOverrides,
      scenarios,
    }),
  })
}

export const profileWeights: Record<Profile, WeightSet> = {
  cost_sensitive: { cost: 0.6, time: 0.15, risk: 0.25 },
  balanced: { cost: 0.4, time: 0.3, risk: 0.3 },
  time_sensitive: { cost: 0.15, time: 0.6, risk: 0.25 },
  reliability_sensitive: { cost: 0.15, time: 0.15, risk: 0.7 },
}
