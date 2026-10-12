import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  analyzeSensitivity,
  explainOptimization,
  getHealth,
  getMetadata,
  listShipments,
  optimizeNewShipment,
  optimizeShipment,
  simulateDisruptions,
} from './api'
import type { DisruptionResponse, HealthResponse, Metadata, NewShipmentOptimization, NewShipmentRequest, OptimizeResponse, Shipment, SensitivityResponse } from './types'

vi.mock('./api', () => ({
  analyzeSensitivity: vi.fn(),
  ApiConnectionError: class ApiConnectionError extends Error {},
  explainOptimization: vi.fn(),
  getHealth: vi.fn(),
  getMetadata: vi.fn(),
  listShipments: vi.fn(),
  optimizeNewShipment: vi.fn(),
  optimizeShipment: vi.fn(),
  simulateDisruptions: vi.fn(),
  profileWeights: {
    cost_sensitive: { cost: 0.6, time: 0.15, risk: 0.25 },
    balanced: { cost: 0.4, time: 0.3, risk: 0.3 },
    time_sensitive: { cost: 0.15, time: 0.6, risk: 0.25 },
    reliability_sensitive: { cost: 0.15, time: 0.15, risk: 0.7 },
  },
}))

const shipment: Shipment = {
  shipment_id: 'S001',
  origin: 'Hamburg, DE',
  destination: 'Sao Paulo, BR',
  cargo_type: 'food',
  weight_kg: 1000,
  distance_km: 5000,
  max_cost_usd: 50000,
  max_transit_days: 30,
  max_delay_probability: 0.8,
  max_congestion_risk: 0.8,
  max_geopolitical_risk: 0.8,
  scenario_class: 'feasible',
  candidate_route_count: 4,
  computed_status: 'feasible',
}

const noRouteShipment: Shipment = {
  ...shipment,
  shipment_id: 'S005',
  scenario_class: 'infeasible',
  computed_status: 'no_feasible_route',
}

const metadata: Metadata = {
  synthetic_data: true,
  shipment_count: 30,
  route_count: 120,
  feasible_route_count: 36,
  infeasible_route_count: 84,
  shipments_with_feasible_routes: 20,
  shipments_without_feasible_routes: 10,
  route_modes: { air: 30, road: 30, rail: 30, ocean: 30 },
  evaluation: {
    profile: 'balanced',
    shipment_count: 30,
    shipments_with_feasible_routes: 20,
    shipments_without_feasible_routes: 10,
    feasibility_label_mismatch_warnings: 0,
    results: {
      weighted_optimizer: {
        count: 20,
        feasibility_rate: 0.6667,
        constraint_violations: 0,
        average_cost_usd: 17000,
        average_transit_days: 19,
        average_risk_penalty: 0.39,
        average_total_penalty: 0.41,
      },
      cheapest_feasible: {
        count: 20,
        feasibility_rate: 0.6667,
        constraint_violations: 0,
        average_cost_usd: 14800,
        average_transit_days: 20,
        average_risk_penalty: 0.42,
        average_total_penalty: 0.42,
      },
      fastest_feasible: {
        count: 20,
        feasibility_rate: 0.6667,
        constraint_violations: 0,
        average_cost_usd: 23000,
        average_transit_days: 17,
        average_risk_penalty: 0.4,
        average_total_penalty: 0.44,
      },
      reliability_oriented: {
        count: 20,
        feasibility_rate: 0.6667,
        constraint_violations: 0,
        average_cost_usd: 18000,
        average_transit_days: 20,
        average_risk_penalty: 0.3,
        average_total_penalty: 0.45,
      },
    },
    profile_sensitivity: {
      balanced: { R0001: 12, R0002: 8 },
      cost_sensitive: { R0001: 15, R0002: 5 },
      time_sensitive: { R0001: 8, R0002: 12 },
      reliability_sensitive: { R0001: 10, R0002: 10 },
    },
    pareto_frontier: {
      eligible_route_count: 36,
      non_dominated_route_count: 25,
      average_frontier_size_per_feasible_shipment: 1.25,
    },
    interpretation: 'Descriptive outcomes on synthetic data.',
  },
}

function recommendedResult(shipmentId: string): OptimizeResponse {
  const route = {
    route_id: 'R0002',
    shipment_id: shipmentId,
    route_mode: 'rail',
    cost_usd: 15000,
    total_cost_usd: 15000,
    transit_time_days: 14,
    delay_probability: 0.2,
    congestion_risk: 0.3,
    geopolitical_risk: 0.2,
    stored_is_feasible: true,
    is_feasible: true,
    feasibility_status: 'feasible' as const,
    rank: 1,
    total_penalty: 0.2,
    risk_penalty: 0.225,
    risk_components: {
      delay_probability: 0.1,
      congestion_risk: 0.075,
      geopolitical_risk: 0.05,
    },
    normalized_scores: { cost: 0.2, time: 0.3, risk: 0.225 },
    weighted_contributions: { cost: 0.08, time: 0.09, risk: 0.0675 },
    competing_routes_ranked_lower: [],
    explanation: 'Selected route R0002.',
    active_weights: { cost: 0.4, time: 0.3, risk: 0.3 },
    active_constraints: {},
    assumptions: ['Illustrative risk coefficients.'],
  }
  return {
    shipment_id: shipmentId,
    status: 'recommended',
    profile: 'balanced',
    weights: { cost: 0.4, time: 0.3, risk: 0.3 },
    constraints: {},
    risk_model: { coefficients: {}, assumption: 'Illustrative.' },
    normalization: 'Min-max among feasible routes.',
    warnings: [],
    recommendation: route,
    ranked_routes: [route],
    rejected_routes: [],
    explanation: 'Selected route R0002.',
  }
}

function sensitivityResult(shipmentId: string): SensitivityResponse {
  return {
    shipment_id: shipmentId,
    points: [
      {
        weights: { cost: 0.6, time: 0.15, risk: 0.25 },
        status: 'recommended',
        selected_route_id: 'R0002',
        total_penalty: 0.2,
      },
      {
        weights: { cost: 0.4, time: 0.3, risk: 0.3 },
        status: 'recommended',
        selected_route_id: 'R0002',
        total_penalty: 0.2,
      },
    ],
    recommendation_counts: { R0002: 2 },
    recommendation_stability: 1,
    route_changes_between_adjacent_points: 0,
    explanation: 'Recommendation stable across tested profiles.',
  }
}

function newShipmentResult(request: NewShipmentRequest): NewShipmentOptimization {
  const noFeasible = request.max_delay_probability === 0 || request.max_congestion_risk === 0
  const shipmentId = 'NEW-1234567890'
  const optimized = recommendedResult(shipmentId)
  if (noFeasible) {
    optimized.status = 'no_feasible_route'
    optimized.recommendation = null
    optimized.ranked_routes = []
    const candidateValues = [
      ['ocean', 28000, 30.6, 0.2233, 0.2453, 0.1871, ['transit_time_days exceeds deadline', 'congestion_risk exceeds limit']],
      ['rail', 36000, 25.2, 0.1503, 0.1963, 0.153, ['congestion_risk exceeds limit']],
      ['road', 45500, 20.7, 0.1733, 0.2178, 0.2208, ['congestion_risk exceeds limit']],
      ['air', 52000, 15.9, 0.1362, 0.2871, 0.2718, ['cost_usd exceeds budget', 'congestion_risk exceeds limit']],
    ] as const
    optimized.rejected_routes = candidateValues.map(([route_mode, cost_usd, transit_time_days, delay_probability, congestion_risk, geopolitical_risk, rejection_reasons], index) => ({
      ...recommendedResult(shipmentId).recommendation!,
      route_id: `${shipmentId}-R${index + 1}`,
      route_mode,
      cost_usd,
      total_cost_usd: cost_usd,
      transit_time_days,
      delay_probability,
      congestion_risk,
      geopolitical_risk,
      is_feasible: false,
      feasibility_status: 'infeasible',
      rank: null,
      total_penalty: null,
      rejection_reasons: ['delay_probability exceeds limit', ...rejection_reasons],
    }))
  }
  return {
    shipment: {
      shipment_id: shipmentId,
      origin: request.origin,
      destination: request.destination,
      cargo_type: request.cargo_type,
      weight_kg: request.weight_kg,
      max_cost_usd: request.max_cost_usd,
      max_transit_days: request.max_transit_days,
      max_delay_probability: request.max_delay_probability,
      max_congestion_risk: request.max_congestion_risk,
      max_geopolitical_risk: request.max_geopolitical_risk,
      estimated_distance_km: 4200,
    },
    candidate_route_source: 'synthetic_estimates',
    synthetic_estimates: true,
    persistence: 'request_only',
    optimization: optimized,
  }
}

function disruptionResult(shipmentId: string): DisruptionResponse {
  const recommendation = recommendedResult(shipmentId).recommendation
  return {
    shipment_id: shipmentId,
    hypothetical: true,
    profile: 'balanced',
    weights: { cost: 0.4, time: 0.3, risk: 0.3 },
    baseline: {
      status: 'recommended',
      recommendation,
      ranked_routes: recommendation ? [recommendation] : [],
      rejected_routes: [],
      feasible_candidate_count: 1,
      candidate_count: 4,
    },
    scenarios: [{
      name: 'Transit pressure',
      parameters: { transit_time_increase_pct: 0.25 },
      status: 'recommended',
      recommendation,
      ranked_routes: recommendation ? [recommendation] : [],
      rejected_routes: [],
      comparison: {
        original_recommendation_route_id: 'R0002',
        disrupted_recommendation_route_id: 'R0002',
        original_recommendation_remains_feasible: true,
        recommendation_changed: false,
        feasible_candidate_count: 1,
        feasible_candidate_percentage: 25,
        baseline_feasible_candidate_count: 1,
        feasible_candidate_change: 0,
        fallback_available: false,
        recommended_cost_change_usd: 0,
        recommended_transit_time_change_days: 3.5,
        recommended_risk_penalty_change: 0,
      },
      routes: [],
      summary: 'Original route R0002 remains the recommendation. 1 of 4 candidates remain feasible.',
    }],
    assumptions: ['Hypothetical deterministic transformation.'],
  }
}

describe('RouteWise dashboard', () => {
  afterEach(() => {
    cleanup()
    window.localStorage.clear()
    window.history.replaceState(null, '', '/')
  })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getHealth).mockResolvedValue({
      status: 'ok',
      dataset_status: 'loaded',
      shipment_count: 30,
      route_count: 120,
    } satisfies HealthResponse)
    vi.mocked(getMetadata).mockResolvedValue(metadata)
    vi.mocked(listShipments).mockResolvedValue([shipment, noRouteShipment])
    vi.mocked(optimizeShipment).mockImplementation(async ({ shipment_id }) =>
      shipment_id === 'S005'
        ? {
            ...recommendedResult(shipment_id),
            status: 'no_feasible_route',
            recommendation: null,
            ranked_routes: [],
            rejected_routes: [],
            explanation: 'No candidate satisfies all constraints.',
          }
        : recommendedResult(shipment_id),
    )
    vi.mocked(optimizeNewShipment).mockImplementation(async (request) => newShipmentResult(request))
    vi.mocked(analyzeSensitivity).mockImplementation(async (shipmentId) =>
      sensitivityResult(shipmentId),
    )
    vi.mocked(explainOptimization).mockResolvedValue({
      shipment_id: 'S001',
      provider_status: 'unavailable',
      source: 'deterministic',
      model: 'openai/gpt-oss-20b',
      narrative: {
        summary: 'The deterministic optimizer selected R0002 using the active weights.',
        tradeoffs: ['The fastest feasible alternative is R0003.'],
        constraint_notes: ['All candidate routes passed active hard constraints.'],
        uncertainties: ['Dataset values are synthetic assumptions.'],
      },
      computed_facts: {
        shipment_id: 'S001',
        status: 'recommended',
        selected_route_id: 'R0002',
        selected_route_mode: 'rail',
        cost_usd: 15000,
        transit_time_days: 14,
        delay_probability: 0.2,
        congestion_risk: 0.3,
        geopolitical_risk: 0.2,
        risk_penalty: 0.225,
        total_penalty: 0.2,
        weighted_contributions: { cost: 0.08, time: 0.09, risk: 0.0675 },
        weights: { cost: 0.4, time: 0.3, risk: 0.3 },
        constraints: {},
        cheapest_feasible: null,
        fastest_feasible: null,
        rejected_route_count: 2,
      },
      warning: 'Groq is not configured; showing a deterministic explanation.',
    })
    vi.mocked(simulateDisruptions).mockImplementation(async (shipmentId) =>
      disruptionResult(shipmentId),
    )
  })

  it('renders measured data and computes a route recommendation through the API', async () => {
    render(<App />)

    expect(await screen.findByText('Shipment intelligence')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Connection status from the RouteWise API health check' })).toHaveTextContent('API connected')
    expect(await screen.findByRole('heading', { name: 'R0002' })).toBeInTheDocument()
    expect(await screen.findByText('Recommendation stable across tested profiles.')).toBeInTheDocument()
    expect(optimizeShipment).toHaveBeenCalledWith(
      expect.objectContaining({ shipment_id: 'S001', profile: 'balanced' }),
    )
  })

  it('switches profiles and shows an explicit no-feasible state', async () => {
    render(<App />)

    await screen.findByRole('heading', { name: 'R0002' })
    fireEvent.change(screen.getByLabelText('Decision profile'), {
      target: { value: 'reliability_sensitive' },
    })
    await waitFor(() => {
      expect(optimizeShipment).toHaveBeenCalledWith(
        expect.objectContaining({ profile: 'reliability_sensitive' }),
      )
    })

    const row = screen.getAllByRole('button', { name: /^S005 food/ })[0]
    expect(row).toBeDefined()
    fireEvent.click(row)
    expect(await screen.findByText('No feasible route found')).toBeInTheDocument()
  })

  it('requests optional analyst commentary and labels optimizer facts separately', async () => {
    render(<App />)

    await screen.findByRole('heading', { name: 'R0002' })
    await userEvent.click(screen.getByRole('button', { name: 'Generate explanation' }))

    expect(await screen.findByText(/The deterministic optimizer selected R0002/)).toBeInTheDocument()
    expect(screen.getByText('Deterministic fallback')).toBeInTheDocument()
    expect(screen.getByLabelText('Optimizer-computed route facts')).toHaveTextContent('$15,000')
    expect(screen.getByText(/AI-generated decision support is not a verified prediction/)).toBeInTheDocument()
    expect(explainOptimization).toHaveBeenCalledWith(
      expect.objectContaining({ shipment_id: 'S001', profile: 'balanced' }),
    )
  })

  it('persists display preferences and navigates using the command palette', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })
    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    fireEvent.change(screen.getByLabelText('Theme'), { target: { value: 'dark' } })
    fireEvent.change(screen.getByLabelText('Currency display'), { target: { value: 'EUR' } })
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(window.localStorage.getItem('routewise.currency')).toBe('EUR')
    fireEvent.click(screen.getByRole('button', { name: 'Close settings' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open command palette' }))
    const palette = within(screen.getByRole('dialog', { name: 'Command palette' }))
    fireEvent.click(palette.getByRole('button', { name: /Disruption lab/ }))
    expect(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: 'Disruption lab' })).toHaveAttribute('aria-current', 'page')
  })

  it('displays INR approximately without changing the canonical optimizer request', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'R0002' })
    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    fireEvent.change(screen.getByLabelText('Currency display'), { target: { value: 'INR' } })
    expect(screen.getByRole('option', { name: 'INR (approx.)' })).toBeInTheDocument()
    expect(window.localStorage.getItem('routewise.currency')).toBe('INR')
    fireEvent.click(screen.getByRole('button', { name: 'Close settings' }))

    expect((await screen.findAllByText('₹4,175,000')).length).toBeGreaterThan(0)
    expect(optimizeShipment).toHaveBeenCalledWith({
      shipment_id: 'S001',
      profile: 'balanced',
      weights: { cost: 0.4, time: 0.3, risk: 0.3 },
      constraint_overrides: {},
    })
  })

  it('provides an explicit disconnected state and retries the health check', async () => {
    vi.mocked(getHealth)
      .mockRejectedValueOnce(new Error('Cannot reach the RouteWise API. Failed to fetch.'))
      .mockResolvedValueOnce({
        status: 'ok',
        dataset_status: 'loaded',
        shipment_count: 30,
        route_count: 120,
      })

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Backend connection unavailable' })).toBeInTheDocument()
    expect(screen.getByText(/Start the backend from the project root/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry connection' }))
    expect(await screen.findByRole('heading', { name: 'Shipment intelligence' })).toBeInTheDocument()
    expect(getHealth).toHaveBeenCalledTimes(2)
  })

  it('uses a compact sidebar with accessible navigation names', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })
    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    fireEvent.click(screen.getByLabelText('Compact sidebar'))
    expect(document.querySelector('.app-shell')).toHaveClass('sidebar-compact')
    expect(window.localStorage.getItem('routewise.sidebarCompact')).toBe('true')
    const navigation = screen.getByRole('navigation', { name: 'Main navigation' })
    expect(within(navigation).getByRole('button', { name: 'Overview' })).toHaveAttribute('data-tooltip', 'Overview')
    expect(within(navigation).getByRole('button', { name: 'Shipments' })).toHaveAttribute('aria-label', 'Shipments')
  })

  it('creates a shipment and displays synthetic route results', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })
    await userEvent.click(screen.getByRole('button', { name: '+ New Shipment' }))
    const dialog = screen.getByRole('dialog', { name: 'Create Shipment' })
    await userEvent.type(within(dialog).getByLabelText('Origin'), 'Hamburg, Germany')
    await userEvent.type(within(dialog).getByLabelText('Destination'), 'Singapore')
    await userEvent.selectOptions(within(dialog).getByLabelText('Cargo type'), 'electronics')
    await userEvent.type(within(dialog).getByLabelText('Cargo weight'), '500')
    await userEvent.type(within(dialog).getByLabelText('Maximum budget'), '50000')
    await userEvent.type(within(dialog).getByLabelText('Delivery deadline'), '30')
    fireEvent.change(within(dialog).getByLabelText('Maximum delay probability'), { target: { value: '0.5' } })
    fireEvent.change(within(dialog).getByLabelText('Maximum congestion risk'), { target: { value: '0.6' } })
    fireEvent.change(within(dialog).getByLabelText('Maximum geopolitical risk'), { target: { value: '0.5' } })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create and optimize' }))

    expect(await screen.findByText('Illustrative synthetic estimates')).toBeInTheDocument()
    expect(screen.getByText(/not carrier quotes, actual distances, or forecasts/)).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'NEW-1234567890 recommendation' })).toBeInTheDocument()
    expect(optimizeNewShipment).toHaveBeenCalledWith(expect.objectContaining({
      origin: 'Hamburg, Germany',
      destination: 'Singapore',
      weight_kg: 500,
      max_cost_usd: 50000,
      max_delay_probability: 0.5,
      max_congestion_risk: 0.6,
      max_geopolitical_risk: 0.5,
    }))
    expect(screen.getByText('Congestion cap')).toBeInTheDocument()
    expect(within(document.querySelector('#shipments') as HTMLElement).getByText('60.0%')).toBeInTheDocument()
    expect(optimizeShipment).not.toHaveBeenCalledWith(expect.objectContaining({
      shipment_id: 'NEW-1234567890',
    }))

    await userEvent.selectOptions(screen.getByLabelText('Decision profile'), 'cost_sensitive')
    await userEvent.click(screen.getByRole('button', { name: 'Optimize selected shipment' }))
    await waitFor(() => {
      expect(optimizeNewShipment).toHaveBeenLastCalledWith(expect.objectContaining({
        origin: 'Hamburg, Germany',
        profile: 'cost_sensitive',
      }))
    })
  }, 15000)

  it('rejects an incomplete create form and displays no-feasible results', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })
    await userEvent.click(screen.getByRole('button', { name: '+ New Shipment' }))
    const dialog = screen.getByRole('dialog', { name: 'Create Shipment' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create and optimize' }))
    expect(optimizeNewShipment).not.toHaveBeenCalled()

    await userEvent.type(within(dialog).getByLabelText('Origin'), 'A')
    await userEvent.type(within(dialog).getByLabelText('Destination'), 'B')
    await userEvent.selectOptions(within(dialog).getByLabelText('Cargo type'), 'electronics')
    await userEvent.type(within(dialog).getByLabelText('Cargo weight'), '100')
    await userEvent.type(within(dialog).getByLabelText('Maximum budget'), '1000')
    await userEvent.type(within(dialog).getByLabelText('Delivery deadline'), '10')
    await userEvent.clear(within(dialog).getByLabelText('Maximum delay probability'))
    await userEvent.type(within(dialog).getByLabelText('Maximum delay probability'), '0')
    await userEvent.clear(within(dialog).getByLabelText('Maximum congestion risk'))
    await userEvent.type(within(dialog).getByLabelText('Maximum congestion risk'), '0')
    await userEvent.clear(within(dialog).getByLabelText('Maximum geopolitical risk'))
    await userEvent.type(within(dialog).getByLabelText('Maximum geopolitical risk'), '0')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create and optimize' }))

    expect(await screen.findByText('No feasible route found')).toBeInTheDocument()
    const candidates = screen.getByRole('region', { name: 'Candidate routes and actual metrics' })
    expect(within(candidates).getAllByRole('row')).toHaveLength(5)
    expect(within(candidates).getByText('24.5%')).toBeInTheDocument()
    expect(within(candidates).getAllByText(/congestion_risk exceeds limit/)).toHaveLength(4)
    expect(within(candidates).getAllByText(/delay_probability exceeds limit/)).toHaveLength(4)
  }, 15000)

  it('opens and closes the same create modal from both visible entry points', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })

    await userEvent.click(screen.getByRole('button', { name: '+ New Shipment' }))
    expect(screen.getByRole('dialog', { name: 'Create Shipment' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close Create Shipment' }))
    expect(screen.queryByRole('dialog', { name: 'Create Shipment' })).not.toBeInTheDocument()

    const explorer = document.querySelector('#shipments') as HTMLElement
    await userEvent.click(within(explorer).getByRole('button', { name: 'Create Shipment' }))
    expect(screen.getByRole('dialog', { name: 'Create Shipment' })).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('dialog', { name: 'Create Shipment' })).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog', { name: 'Create Shipment' })).not.toBeInTheDocument()
  })

  it('updates the active navigation item as the main content scrolls in both directions', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })
    const main = document.querySelector('.main-content') as HTMLElement
    const positions: Record<string, number> = {
      overview: 90,
      shipments: 800,
      'decision-lab': 1500,
      'disruption-lab': 2200,
      evaluation: 2900,
    }
    Object.defineProperty(main, 'clientHeight', { configurable: true, value: 600 })
    Object.defineProperty(main, 'scrollHeight', { configurable: true, value: 3500 })
    const rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
      if (this === main) return new DOMRect(0, 0, 1000, 600)
      const sectionId = (this as HTMLElement).id
      if (sectionId in positions) {
        return new DOMRect(0, positions[sectionId] - main.scrollTop, 1000, 300)
      }
      return new DOMRect(0, 0, 1000, 20)
    })
    const navigation = screen.getByRole('navigation', { name: 'Main navigation' })
    const expectActive = async (section: string) => {
      await waitFor(() => {
        const label = section === 'decision-lab'
          ? 'Decision lab'
          : section === 'disruption-lab'
            ? 'Disruption lab'
            : section[0].toUpperCase() + section.slice(1)
        expect(within(navigation).getByRole('button', { name: label })).toHaveAttribute('aria-current', 'page')
      })
    }
    const scrollTo = async (top: number, section: string) => {
      main.scrollTop = top
      fireEvent.scroll(main)
      await expectActive(section)
    }

    await scrollTo(0, 'overview')
    await scrollTo(800, 'shipments')
    await scrollTo(1500, 'decision-lab')
    await scrollTo(2200, 'disruption-lab')
    await scrollTo(2900, 'evaluation')
    await scrollTo(0, 'overview')

    rectSpy.mockRestore()
  })

  it('updates navigation immediately on click and follows browser hash history', async () => {
    const scrollIntoView = vi.fn()
    HTMLElement.prototype.scrollIntoView = scrollIntoView
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })
    const navigation = screen.getByRole('navigation', { name: 'Main navigation' })
    await userEvent.click(within(navigation).getByRole('button', { name: 'Decision lab' }))
    expect(within(navigation).getByRole('button', { name: 'Decision lab' })).toHaveAttribute('aria-current', 'page')
    expect(window.location.hash).toBe('#decision-lab')
    expect(scrollIntoView).toHaveBeenCalled()

    window.location.hash = '#evaluation'
    await waitFor(() => {
      expect(within(navigation).getByRole('button', { name: 'Evaluation' })).toHaveAttribute('aria-current', 'page')
    })
  })

  it('renders chart axes and a recommended route tooltip from the selected shipment only', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'R0002' })
    const chart = await screen.findByRole('img', { name: /Candidate routes for the selected shipment/ })
    expect(chart).toHaveTextContent('Cost (USD)')
    expect(chart).toHaveTextContent('Transit time (days)')
    expect(document.querySelector('.scatter-marker[aria-label^="R0002, rail"]')).toHaveClass('recommended')
  })

  it('runs and renders API-backed hypothetical disruption scenarios', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('heading', { name: 'Shipment intelligence' })
    await screen.findAllByRole('option', { name: /R0002/ })
    await user.selectOptions(
      screen.getByRole('listbox', { name: 'Transit pressure affected route IDs' }),
      'R0002',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Run hypothetical simulation' }))
    expect(await screen.findByText(/Original route R0002 remains the recommendation/)).toBeInTheDocument()
    expect(screen.getByText('FEASIBLE CANDIDATES')).toBeInTheDocument()
    expect(simulateDisruptions).toHaveBeenCalledWith(
      'S001',
      expect.arrayContaining([
        expect.objectContaining({ name: 'Transit pressure', transit_time_increase_pct: 0.25, route_ids: ['R0002'] }),
      ]),
      'balanced',
      { cost: 0.4, time: 0.3, risk: 0.3 },
      {},
    )
  })
})
