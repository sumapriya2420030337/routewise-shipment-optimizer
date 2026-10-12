import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  analyzeSensitivity,
  ApiConnectionError,
  getHealth,
  getMetadata,
  listShipments,
  explainOptimization,
  optimizeNewShipment,
  optimizeShipment,
  profileWeights,
  simulateDisruptions,
} from './api'
import { convertUsdForDisplay, formatCurrency, formatCurrencyTick, type DisplayCurrency } from './currency'
import type {
  ConstraintOverrides,
  AnalystExplanation,
  DisruptionResponse,
  DisruptionScenarioInput,
  Evaluation,
  Metadata,
  NewShipmentOptimization,
  NewShipmentRequest,
  OptimizeRequest,
  OptimizeResponse,
  Profile,
  RouteCandidate,
  SensitivityResponse,
  Shipment,
  WeightSet,
} from './types'
import { RouteMap } from './RouteMap'
import './App.css'

const profileNames: Record<Profile, string> = {
  cost_sensitive: 'Cost-sensitive',
  balanced: 'Balanced',
  time_sensitive: 'Time-sensitive',
  reliability_sensitive: 'Reliability-focused',
}

const profileDescriptions: Record<Profile, string> = {
  cost_sensitive: 'Prioritize lower spend while preserving service and risk.',
  balanced: 'Balance cost, time, and the illustrative risk score.',
  time_sensitive: 'Favor faster eligible routes.',
  reliability_sensitive: 'Favor lower delay, congestion, and geopolitical risk.',
}

const constraintFields: Array<{
  key: keyof ConstraintOverrides
  label: string
  unit: string
}> = [
  { key: 'max_cost_usd', label: 'Budget ceiling', unit: 'USD' },
  { key: 'max_transit_days', label: 'Delivery deadline', unit: 'days' },
  { key: 'max_delay_probability', label: 'Delay probability cap', unit: '0–1' },
  { key: 'max_congestion_risk', label: 'Congestion risk cap', unit: '0–1' },
  { key: 'max_geopolitical_risk', label: 'Geopolitical risk cap', unit: '0–1' },
]

type Theme = 'light' | 'dark' | 'system'
type Density = 'comfortable' | 'compact'
type ShipmentSort = 'shipment_id' | 'max_cost_usd' | 'max_transit_days'
type NewShipmentFormValues = {
  origin: string
  destination: string
  cargo_type: string
  weight_kg: string
  max_cost_usd: string
  max_transit_days: string
  max_delay_probability: string
  max_congestion_risk: string
  max_geopolitical_risk: string
}

const emptyNewShipmentForm: NewShipmentFormValues = {
  origin: '',
  destination: '',
  cargo_type: '',
  weight_kg: '',
  max_cost_usd: '',
  max_transit_days: '',
  max_delay_probability: '0.8',
  max_congestion_risk: '0.8',
  max_geopolitical_risk: '0.8',
}

const sectionNames: Record<string, string> = {
  overview: 'Overview',
  shipments: 'Shipments',
  'decision-lab': 'Decision lab',
  'disruption-lab': 'Disruption lab',
  evaluation: 'Evaluation',
}

const sectionOrder = Object.keys(sectionNames)

function sectionFromHash(hash: string): string | null {
  const section = decodeURIComponent(hash.replace(/^#/, ''))
  return sectionOrder.includes(section) ? section : null
}

function initialPreference<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T,
): T {
  const stored = window.localStorage.getItem(key)
  if (stored && allowed.includes(stored as T)) return stored as T
  return fallback
}

function currency(value: number, displayCurrency: DisplayCurrency = 'USD'): string {
  return formatCurrency(value, displayCurrency)
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function displayName(value: string): string {
  return value.replaceAll('_', ' ')
}

function ChartBar({
  label,
  value,
  max,
  color = 'blue',
  suffix = '',
}: {
  label: string
  value: number
  max: number
  color?: string
  suffix?: string
}) {
  const width = max > 0 ? Math.max(2, (value / max) * 100) : 0
  return (
    <div className="chart-bar-row">
      <span className="chart-bar-label">{label}</span>
      <div className="chart-track" aria-hidden="true">
        <span className={`chart-bar ${color}`} style={{ width: `${width}%` }} />
      </div>
      <strong className="chart-bar-value">{value.toFixed(1)}{suffix}</strong>
    </div>
  )
}

function RouteScatterChart({
  routes,
  displayCurrency,
  recommendedRouteId,
  selectedRouteId,
  onSelect,
}: {
  routes: RouteCandidate[]
  displayCurrency: DisplayCurrency
  recommendedRouteId?: string
  selectedRouteId: string
  onSelect: (routeId: string) => void
}) {
  if (routes.length === 0) {
    return <div className="empty-state">Select a shipment and load its candidates to compare cost and transit time.</div>
  }

  const left = 82
  const right = 666
  const top = 24
  const bottom = 238
  const costs = routes.map((route) => route.cost_usd)
  const days = routes.map((route) => route.transit_time_days)
  const minCost = Math.min(...costs)
  const maxCost = Math.max(...costs)
  const minDays = Math.min(...days)
  const maxDays = Math.max(...days)
  const tickFractions = [0, 0.25, 0.5, 0.75, 1]
  const xFor = (value: number) => left + ((value - minCost) / (maxCost - minCost || 1)) * (right - left)
  const yFor = (value: number) => bottom - ((value - minDays) / (maxDays - minDays || 1)) * (bottom - top)

  return (
    <div className="scatter-wrap">
      <svg
        aria-label={`Candidate routes for the selected shipment, cost in ${displayCurrency} and transit time in days`}
        className="scatter-chart"
        role="img"
        viewBox="0 0 710 292"
      >
        <title>Route cost versus transit time</title>
        {tickFractions.map((fraction) => {
          const x = left + fraction * (right - left)
          const y = bottom - fraction * (bottom - top)
          const tickCost = minCost + fraction * (maxCost - minCost)
          const tickDays = minDays + fraction * (maxDays - minDays)
          return (
            <g key={fraction}>
              <line className="scatter-gridline" x1={x} x2={x} y1={top} y2={bottom} />
              <line className="scatter-gridline" x1={left} x2={right} y1={y} y2={y} />
              <text className="scatter-tick" textAnchor="middle" x={x} y={bottom + 19}>
                {formatCurrencyTick(tickCost, displayCurrency)}
              </text>
              <text className="scatter-tick" textAnchor="end" x={left - 10} y={y + 4}>
                {tickDays.toFixed(1)}
              </text>
            </g>
          )
        })}
        <line className="scatter-axis" x1={left} x2={right} y1={bottom} y2={bottom} />
        <line className="scatter-axis" x1={left} x2={left} y1={top} y2={bottom} />
        <text className="scatter-label" textAnchor="middle" x={(left + right) / 2} y="284">
          Cost ({displayCurrency})
        </text>
        <text className="scatter-label" textAnchor="middle" transform={`translate(17 ${(top + bottom) / 2}) rotate(-90)`}>
          Transit time (days)
        </text>
        {routes.map((route) => {
          const feasible = route.is_feasible
          const recommended = feasible && route.route_id === recommendedRouteId
          const accessibleText = `${route.route_id}, ${route.route_mode}, ${currency(route.cost_usd, displayCurrency)}, ${route.transit_time_days.toFixed(1)} days, ${feasible ? 'feasible' : 'infeasible'}, delay ${percent(route.delay_probability)}, congestion risk ${percent(route.congestion_risk)}, geopolitical risk ${percent(route.geopolitical_risk)}`
          const x = xFor(route.cost_usd)
          const y = yFor(route.transit_time_days)
          return (
            <g
              aria-label={accessibleText}
              className={`scatter-marker ${feasible ? 'feasible' : 'infeasible'} ${recommended ? 'recommended' : ''} ${route.route_id === selectedRouteId ? 'selected' : ''}`}
              key={route.route_id}
              onClick={() => onSelect(route.route_id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelect(route.route_id)
                }
              }}
              role="button"
              tabIndex={0}
              transform={`translate(${x} ${y})`}
            >
              <title>{accessibleText}</title>
              {recommended && <circle className="scatter-recommendation-ring" r="11" />}
              {feasible ? <circle className="scatter-point" r={recommended ? 7 : 6} /> : <path className="scatter-point" d="M 0 -7 L 7 0 L 0 7 L -7 0 Z" />}
            </g>
          )
        })}
      </svg>
      <div aria-label="Route eligibility legend" className="scatter-legend">
        <span><i className="scatter-feasible" />Feasible candidate</span>
        <span><i className="scatter-infeasible" />Infeasible candidate</span>
        <span><i className="scatter-recommended" />Recommended</span>
      </div>
    </div>
  )
}

function App() {
  const [theme, setTheme] = useState<Theme>(() =>
    initialPreference('routewise.theme', ['light', 'dark', 'system'], 'system'),
  )
  const [density, setDensity] = useState<Density>(() =>
    initialPreference('routewise.density', ['comfortable', 'compact'], 'comfortable'),
  )
  const [currencyDisplay, setCurrencyDisplay] = useState<DisplayCurrency>(() =>
    initialPreference('routewise.currency', ['USD', 'EUR', 'GBP', 'INR'], 'USD'),
  )
  const [reducedMotion, setReducedMotion] = useState(
    () => window.localStorage.getItem('routewise.reducedMotion') === 'true',
  )
  const [sidebarCompact, setSidebarCompact] = useState(
    () => window.localStorage.getItem('routewise.sidebarCompact') === 'true',
  )
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteQuery, setPaletteQuery] = useState('')
  const [toast, setToast] = useState('')
  const [activity, setActivity] = useState<Array<{ text: string; at: string }>>([])
  const [disruptionScenarios, setDisruptionScenarios] = useState<DisruptionScenarioInput[]>([
    {
      name: 'Transit pressure',
      delay_probability_increase: 0,
      congestion_risk_increase: 0,
      geopolitical_risk_increase: 0,
      transit_time_increase_pct: 0.25,
      cost_increase_pct: 0,
      route_modes: [],
      route_ids: [],
    },
    {
      name: 'Cost pressure',
      delay_probability_increase: 0,
      congestion_risk_increase: 0,
      geopolitical_risk_increase: 0,
      transit_time_increase_pct: 0,
      cost_increase_pct: 0.2,
      route_modes: [],
      route_ids: [],
    },
  ])
  const [disruptionResult, setDisruptionResult] = useState<DisruptionResponse | null>(null)
  const [simulating, setSimulating] = useState(false)
  const [simulationError, setSimulationError] = useState('')
  const [selectedSimulationIndex, setSelectedSimulationIndex] = useState(0)
  const toastTimer = useRef<number | undefined>(undefined)
  const commandInput = useRef<HTMLInputElement>(null)
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const [apiConnected, setApiConnected] = useState(false)
  const [shipments, setShipments] = useState<Shipment[]>([])
  const [createdShipments, setCreatedShipments] = useState<Shipment[]>([])
  const [createdRequests, setCreatedRequests] = useState<Record<string, NewShipmentRequest>>({})
  const [activeCreatedResult, setActiveCreatedResult] = useState<NewShipmentOptimization | null>(null)
  const [createShipmentOpen, setCreateShipmentOpen] = useState(false)
  const [creatingShipment, setCreatingShipment] = useState(false)
  const [createShipmentError, setCreateShipmentError] = useState('')
  const [newShipmentForm, setNewShipmentForm] = useState<NewShipmentFormValues>(emptyNewShipmentForm)
  const [selectedShipmentId, setSelectedShipmentId] = useState('')
  const [shipmentFilter, setShipmentFilter] = useState<'all' | 'feasible' | 'no_feasible_route'>('all')
  const [shipmentSort, setShipmentSort] = useState<{ key: ShipmentSort; descending: boolean }>({
    key: 'shipment_id',
    descending: false,
  })
  const [selectedRouteId, setSelectedRouteId] = useState('')
  const [compareRouteIds, setCompareRouteIds] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [profile, setProfile] = useState<Profile | 'custom'>('balanced')
  const [weights, setWeights] = useState<WeightSet>(profileWeights.balanced)
  const [overrides, setOverrides] = useState<ConstraintOverrides>({})
  const [optimization, setOptimization] = useState<OptimizeResponse | null>(null)
  const [analystExplanation, setAnalystExplanation] = useState<AnalystExplanation | null>(null)
  const [analystLoading, setAnalystLoading] = useState(false)
  const [analystError, setAnalystError] = useState('')
  const [sensitivity, setSensitivity] = useState<SensitivityResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [retrying, setRetrying] = useState(false)
  const [optimizing, setOptimizing] = useState(false)
  const [sensitivityLoading, setSensitivityLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeSection, setActiveSection] = useState(
    () => sectionFromHash(window.location.hash) ?? 'overview',
  )
  const mainContentRef = useRef<HTMLElement>(null)
  const navigationLockRef = useRef<string | null>(null)
  const navigationTimerRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const applyTheme = () => {
      document.documentElement.dataset.theme =
        theme === 'system' ? (media?.matches ? 'dark' : 'light') : theme
    }
    applyTheme()
    media?.addEventListener('change', applyTheme)
    window.localStorage.setItem('routewise.theme', theme)
    return () => media?.removeEventListener('change', applyTheme)
  }, [theme])
  useEffect(() => {
    document.documentElement.dataset.density = density
    window.localStorage.setItem('routewise.density', density)
  }, [density])
  useEffect(() => {
    document.documentElement.dataset.reducedMotion = String(reducedMotion)
    window.localStorage.setItem('routewise.reducedMotion', String(reducedMotion))
  }, [reducedMotion])
  useEffect(() => {
    window.localStorage.setItem('routewise.currency', currencyDisplay)
  }, [currencyDisplay])
  useEffect(() => {
    window.localStorage.setItem('routewise.sidebarCompact', String(sidebarCompact))
  }, [sidebarCompact])
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen(true)
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false)
        setSettingsOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
  useEffect(() => {
    if (paletteOpen) commandInput.current?.focus()
  }, [paletteOpen])
  useEffect(() => {
    if (!toast) return
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    const timer = window.setTimeout(() => setToast(''), 2800)
    toastTimer.current = timer
    return () => window.clearTimeout(timer)
  }, [toast])

  const selectedShipment = useMemo(
    () => [...shipments, ...createdShipments].find((shipment) => shipment.shipment_id === selectedShipmentId) ?? null,
    [createdShipments, shipments, selectedShipmentId],
  )
  const selectedIsCreated = selectedShipmentId in createdRequests
  const weightTotal = weights.cost + weights.time + weights.risk
  const weightsValid = Math.abs(weightTotal - 1) <= 1e-9
  const evaluation: Evaluation | undefined = metadata?.evaluation
  const visibleShipments = [...shipments, ...createdShipments]
    .filter((shipment) => shipmentFilter === 'all' || shipment.computed_status === shipmentFilter)
    .filter((shipment) => shipments.includes(shipment) || (
      `${shipment.shipment_id} ${shipment.origin} ${shipment.destination} ${shipment.cargo_type}`
        .toLowerCase().includes(search.toLowerCase())
    ))
    .sort((left, right) => {
      const first = left[shipmentSort.key]
      const second = right[shipmentSort.key]
      const comparison = typeof first === 'string' && typeof second === 'string'
        ? first.localeCompare(second)
        : Number(first) - Number(second)
      return shipmentSort.descending ? -comparison : comparison
    })

  const toggleShipmentSort = (key: ShipmentSort) => {
    setShipmentSort((current) => ({
      key,
      descending: current.key === key ? !current.descending : false,
    }))
  }
  const routeCandidates = [
    ...(optimization?.shipment_id === selectedShipmentId ? optimization.ranked_routes : []),
    ...(optimization?.shipment_id === selectedShipmentId ? optimization.rejected_routes : []),
  ]
  const selectedRoute = routeCandidates.find((route) => route.route_id === selectedRouteId)
  const selectedMapRoute = selectedRoute?.is_feasible
    ? selectedRoute
    : optimization?.recommendation ?? null
  const comparedRoutes = routeCandidates.filter((route) => compareRouteIds.includes(route.route_id))
  const paletteShipments = [...shipments, ...createdShipments].filter((shipment) =>
    `${shipment.shipment_id} ${shipment.origin} ${shipment.destination} ${shipment.cargo_type}`
      .toLowerCase()
      .includes(paletteQuery.toLowerCase()),
  ).slice(0, 5)

  useEffect(() => {
    let active = true
    Promise.all([getHealth(), getMetadata(), listShipments()])
      .then(([health, loadedMetadata, loadedShipments]) => {
        if (!active) return
        if (health.status !== 'ok' || health.dataset_status !== 'loaded') {
          throw new Error('The RouteWise API is running but its dataset is not ready.')
        }
        setMetadata(loadedMetadata)
        setShipments(loadedShipments)
        setSelectedShipmentId(loadedShipments[0]?.shipment_id ?? '')
        setApiConnected(true)
        setLoading(false)
      })
      .catch((reason: unknown) => {
        if (!active) return
        setError(
          reason instanceof ApiConnectionError
            ? `${reason.message} Start the backend in a separate terminal, then retry.`
            : reason instanceof Error
              ? reason.message
              : 'Could not load RouteWise data.',
        )
        setApiConnected(false)
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (loading || !apiConnected) return
    let active = true
    const timer = window.setTimeout(() => {
      listShipments(search)
        .then((rows) => {
          if (!active) return
          setShipments(rows)
          setSelectedShipmentId((current) =>
            rows.some((row) => row.shipment_id === current) ||
            createdShipments.some((row) => row.shipment_id === current)
              ? current
              : rows[0]?.shipment_id ?? '',
          )
        })
        .catch((reason: unknown) => {
          if (active) {
            if (reason instanceof ApiConnectionError) setApiConnected(false)
            setError(reason instanceof Error ? reason.message : 'Shipment search failed.')
          }
        })
    }, 180)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [apiConnected, createdShipments, loading, search])

  const recalculate = useCallback(async () => {
    if (!selectedShipmentId || !weightsValid) return
    setOptimizing(true)
    setAnalystExplanation(null)
    setAnalystError('')
    setError('')
    const activeProfile = profile === 'custom' ? 'balanced' : profile
    const createdRequest = createdRequests[selectedShipmentId]
    if (createdRequest) {
      try {
        const result = await optimizeNewShipment({
          ...createdRequest,
          profile: activeProfile,
          weights,
          constraint_overrides: overrides,
        })
        setActiveCreatedResult(result)
        setOptimization(result.optimization)
        setSensitivity(null)
        setActivity((items) => [
          {
            text: `${selectedShipmentId}: ${result.optimization.recommendation?.route_id ?? 'no feasible route'}`,
            at: new Date().toLocaleTimeString(),
          },
          ...items,
        ].slice(0, 6))
      } catch (reason: unknown) {
        if (reason instanceof ApiConnectionError) setApiConnected(false)
        setError(reason instanceof Error ? reason.message : 'New shipment optimization failed.')
        setOptimization(null)
      } finally {
        setOptimizing(false)
      }
      return
    }
    setSensitivityLoading(true)
    const points = [
      profileWeights.cost_sensitive,
      profileWeights.balanced,
      profileWeights.time_sensitive,
      profileWeights.reliability_sensitive,
      { cost: 0.8, time: 0.1, risk: 0.1 },
      { cost: 0.1, time: 0.1, risk: 0.8 },
      weights,
    ]
    const [recommendationResult, sensitivityResult] = await Promise.allSettled([
      optimizeShipment({
        shipment_id: selectedShipmentId,
        profile: activeProfile,
        weights,
        constraint_overrides: overrides,
      }),
      analyzeSensitivity(selectedShipmentId, points, overrides),
    ])
    if (recommendationResult.status === 'fulfilled') {
      setOptimization(recommendationResult.value)
      setActivity((items) => [
        {
          text: `${selectedShipmentId}: ${recommendationResult.value.recommendation?.route_id ?? 'no feasible route'}`,
          at: new Date().toLocaleTimeString(),
        },
        ...items,
      ].slice(0, 6))
    } else {
      if (recommendationResult.reason instanceof ApiConnectionError) setApiConnected(false)
      setError(
        recommendationResult.reason instanceof Error
          ? recommendationResult.reason.message
          : 'Optimization failed.',
      )
      setOptimization(null)
    }
    if (sensitivityResult.status === 'fulfilled') {
      setSensitivity(sensitivityResult.value)
    } else {
      if (sensitivityResult.reason instanceof ApiConnectionError) setApiConnected(false)
      setSensitivity(null)
      setError((current) =>
        current ||
        (sensitivityResult.reason instanceof Error
          ? sensitivityResult.reason.message
          : 'Sensitivity analysis failed.'),
      )
    }
    setOptimizing(false)
    setSensitivityLoading(false)
  }, [createdRequests, overrides, profile, selectedShipmentId, weights, weightsValid])

  const createShipment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setCreateShipmentError('')
    setCreatingShipment(true)
    const request: NewShipmentRequest = {
      origin: newShipmentForm.origin.trim(),
      destination: newShipmentForm.destination.trim(),
      cargo_type: newShipmentForm.cargo_type.trim(),
      weight_kg: Number(newShipmentForm.weight_kg),
      max_cost_usd: Number(newShipmentForm.max_cost_usd),
      max_transit_days: Number(newShipmentForm.max_transit_days),
      max_delay_probability: Number(newShipmentForm.max_delay_probability),
      max_congestion_risk: Number(newShipmentForm.max_congestion_risk),
      max_geopolitical_risk: Number(newShipmentForm.max_geopolitical_risk),
      profile: profile === 'custom' ? 'balanced' : profile,
      weights,
      constraint_overrides: {},
    }

    try {
      const result = await optimizeNewShipment(request)
      const created: Shipment = {
        ...result.shipment,
        distance_km: result.shipment.estimated_distance_km,
        candidate_route_count:
          result.optimization.ranked_routes.length + result.optimization.rejected_routes.length,
        scenario_class: result.optimization.status === 'recommended' ? 'feasible' : 'infeasible',
        computed_status:
          result.optimization.status === 'recommended' ? 'feasible' : 'no_feasible_route',
      }
      setCreatedShipments((items) => [
        ...items.filter((item) => item.shipment_id !== created.shipment_id),
        created,
      ])
      setCreatedRequests((items) => ({ ...items, [created.shipment_id]: request }))
      setActiveCreatedResult(result)
      setSelectedShipmentId(created.shipment_id)
      setOverrides({})
      setOptimization(result.optimization)
      setSensitivity(null)
      setSelectedRouteId('')
      setCompareRouteIds([])
      setCreateShipmentOpen(false)
      setToast('Shipment optimized. This result is available for this session only.')
      setActivity((items) => [
        {
          text: `${created.shipment_id}: ${result.optimization.recommendation?.route_id ?? 'no feasible route'}`,
          at: new Date().toLocaleTimeString(),
        },
        ...items,
      ].slice(0, 6))
    } catch (reason: unknown) {
      if (reason instanceof ApiConnectionError) setApiConnected(false)
      setCreateShipmentError(reason instanceof Error ? reason.message : 'Could not create shipment.')
    } finally {
      setCreatingShipment(false)
    }
  }

  const updateNewShipmentForm = (field: keyof NewShipmentFormValues, value: string) => {
    setNewShipmentForm((current) => ({ ...current, [field]: value }))
  }

  const requestAnalystExplanation = async () => {
    if (!selectedShipmentId || selectedIsCreated || !weightsValid || optimizing || !optimization) return
    const request: OptimizeRequest = {
      shipment_id: selectedShipmentId,
      profile: profile === 'custom' ? 'balanced' : profile,
      weights,
      constraint_overrides: overrides,
    }
    setAnalystLoading(true)
    setAnalystError('')
    try {
      setAnalystExplanation(await explainOptimization(request))
    } catch (reason) {
      if (reason instanceof ApiConnectionError) setApiConnected(false)
      setAnalystError(
        reason instanceof Error
          ? reason.message
          : 'Could not request an analyst explanation.',
      )
    } finally {
      setAnalystLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void recalculate()
    }, 120)
    return () => window.clearTimeout(timer)
  }, [recalculate])

  const chooseSection = (section: string) => {
    if (!sectionOrder.includes(section)) return
    setActiveSection(section)
    navigationLockRef.current = section
    if (navigationTimerRef.current !== undefined) {
      window.clearTimeout(navigationTimerRef.current)
    }
    if (window.location.hash !== `#${section}`) {
      window.history.pushState(null, '', `#${section}`)
    }
    document.getElementById(section)?.scrollIntoView?.({
      behavior: reducedMotion ? 'auto' : 'smooth',
      block: 'start',
    })
    if (reducedMotion) {
      navigationLockRef.current = null
    } else {
      navigationTimerRef.current = window.setTimeout(() => {
        navigationLockRef.current = null
        syncActiveSection()
      }, 2500)
    }
    setPaletteOpen(false)
  }

  const syncActiveSection = useCallback(() => {
    const main = mainContentRef.current
    if (!main || navigationLockRef.current) return
    const activationLine = Math.max(96, Math.min(160, window.innerHeight * 0.2))
    let visibleSection = sectionOrder[0]
    for (const section of sectionOrder) {
      const element = document.getElementById(section)
      if (element && element.getBoundingClientRect().top <= activationLine) {
        visibleSection = section
      } else {
        break
      }
    }
    if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
      visibleSection = sectionOrder[sectionOrder.length - 1]
    }
    setActiveSection((current) => current === visibleSection ? current : visibleSection)
  }, [])

  useEffect(() => {
    const main = mainContentRef.current
    if (!main) return

    const releaseNavigation = () => {
      if (!navigationLockRef.current) return
      if (navigationTimerRef.current !== undefined) {
        window.clearTimeout(navigationTimerRef.current)
        navigationTimerRef.current = undefined
      }
      navigationLockRef.current = null
      syncActiveSection()
    }
    const navigateFromLocation = () => {
      const section = sectionFromHash(window.location.hash)
      if (!section) {
        if (navigationTimerRef.current !== undefined) {
          window.clearTimeout(navigationTimerRef.current)
          navigationTimerRef.current = undefined
        }
        navigationLockRef.current = null
        syncActiveSection()
        return
      }
      setActiveSection(section)
      navigationLockRef.current = section
      document.getElementById(section)?.scrollIntoView?.({
        behavior: reducedMotion ? 'auto' : 'smooth',
        block: 'start',
      })
      if (navigationTimerRef.current !== undefined) {
        window.clearTimeout(navigationTimerRef.current)
      }
      if (reducedMotion) {
        navigationLockRef.current = null
      } else {
        navigationTimerRef.current = window.setTimeout(releaseNavigation, 2500)
      }
    }
    const onResize = () => syncActiveSection()

    const onScroll = () => {
      if (!navigationLockRef.current) syncActiveSection()
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('scrollend', releaseNavigation)
    window.addEventListener('resize', onResize)
    window.addEventListener('popstate', navigateFromLocation)
    window.addEventListener('hashchange', navigateFromLocation)

    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(onResize)
    resizeObserver?.observe(main)
    for (const section of sectionOrder) {
      const element = document.getElementById(section)
      if (element) resizeObserver?.observe(element)
    }

    const initialSection = sectionFromHash(window.location.hash)
    if (initialSection) {
      window.requestAnimationFrame(navigateFromLocation)
    } else {
      syncActiveSection()
    }

    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('scrollend', releaseNavigation)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('popstate', navigateFromLocation)
      window.removeEventListener('hashchange', navigateFromLocation)
      resizeObserver?.disconnect()
      if (navigationTimerRef.current !== undefined) {
        window.clearTimeout(navigationTimerRef.current)
        navigationTimerRef.current = undefined
      }
      navigationLockRef.current = null
    }
  }, [loading, reducedMotion, sidebarCompact, syncActiveSection])

  const chooseShipment = (shipmentId: string) => {
    setSelectedShipmentId(shipmentId)
    setOverrides({})
    setSelectedRouteId('')
    setCompareRouteIds([])
    setDisruptionResult(null)
    setSimulationError('')
    setSelectedSimulationIndex(0)
  }

  const updateScenario = (
    index: number,
    patch: Partial<DisruptionScenarioInput>,
  ) => {
    setDisruptionScenarios((current) =>
      current.map((scenario, itemIndex) =>
        itemIndex === index ? { ...scenario, ...patch } : scenario,
      ),
    )
  }

  const runDisruptionSimulation = async () => {
    if (!selectedShipmentId || !weightsValid) return
    setSimulating(true)
    setSimulationError('')
    try {
      const result = await simulateDisruptions(
        selectedShipmentId,
        disruptionScenarios,
        profile === 'custom' ? 'balanced' : profile,
        weights,
        overrides,
      )
      setDisruptionResult(result)
      setSelectedSimulationIndex(0)
      setActivity((items) => [
        { text: `${selectedShipmentId}: ran ${result.scenarios.length} hypothetical disruption(s)`, at: new Date().toLocaleTimeString() },
        ...items,
      ].slice(0, 6))
      setToast('Hypothetical disruption simulation completed.')
    } catch (reason: unknown) {
    if (reason instanceof ApiConnectionError) setApiConnected(false)
    setSimulationError(reason instanceof Error ? reason.message : 'Disruption simulation failed.')
    } finally {
      setSimulating(false)
    }
  }

  const refreshWorkspace = async () => {
    setRetrying(true)
    try {
      const health = await getHealth()
      if (health.status !== 'ok' || health.dataset_status !== 'loaded') {
        throw new Error('The RouteWise API is running but its dataset is not ready.')
      }
      const [nextMetadata, nextShipments] = await Promise.all([getMetadata(), listShipments(search)])
      setMetadata(nextMetadata)
      setShipments(nextShipments)
      setSelectedShipmentId((current) =>
        nextShipments.some((shipment) => shipment.shipment_id === current) ||
        createdShipments.some((shipment) => shipment.shipment_id === current)
          ? current
          : nextShipments[0]?.shipment_id ?? '',
      )
      setApiConnected(true)
      setError('')
      setToast('RouteWise data refreshed.')
    } catch (reason: unknown) {
      setApiConnected(false)
      setError(
        reason instanceof ApiConnectionError
          ? `${reason.message} Start the backend in a separate terminal, then retry.`
          : reason instanceof Error
            ? reason.message
            : 'Could not refresh RouteWise data.',
      )
    } finally {
      setRetrying(false)
    }
  }

  const openCreateShipment = () => {
    setCreateShipmentError('')
    setCreateShipmentOpen(true)
  }

  const selectCommandShipment = (shipmentId: string) => {
    setSearch(shipmentId)
    chooseShipment(shipmentId)
    chooseSection('shipments')
  }

  const exportCsv = (filename: string, rows: Array<Record<string, string | number | boolean | null | undefined>>) => {
    if (!rows.length) return
    const headers = Object.keys(rows[0])
    const escapeCsv = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const body = [headers.map(escapeCsv).join(','), ...rows.map((row) => headers.map((key) => escapeCsv(row[key])).join(','))].join('\r\n')
    const url = URL.createObjectURL(new Blob([body], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
    setToast(`${filename} downloaded.`)
  }

  const changeWeight = (key: keyof WeightSet, rawValue: string) => {
    const value = Number(rawValue)
    setProfile('custom')
    setWeights((previous) => ({ ...previous, [key]: Number.isFinite(value) ? value : 0 }))
  }

  const changeConstraint = (key: keyof ConstraintOverrides, rawValue: string) => {
    setOverrides((previous) => {
      if (!rawValue.trim()) {
        const next = { ...previous }
        delete next[key]
        return next
      }
      const value = Number(rawValue)
      if (!Number.isFinite(value)) return previous
      return { ...previous, [key]: value }
    })
  }

  const chooseProfile = (nextProfile: Profile) => {
    setProfile(nextProfile)
    setWeights(profileWeights[nextProfile])
  }

  const evaluationEntries = evaluation
    ? Object.entries(evaluation.results)
    : []
  const maxModeCount = metadata
    ? Math.max(...Object.values(metadata.route_modes), 1)
    : 1
  const costMax = Math.max(...evaluationEntries.map(([, row]) => convertUsdForDisplay(row.average_cost_usd, currencyDisplay)), 1)
  const timeMax = Math.max(...evaluationEntries.map(([, row]) => row.average_transit_days), 1)
  const riskMax = Math.max(...evaluationEntries.map(([, row]) => row.average_risk_penalty), 1)

  if (loading) {
    return (
      <main className="loading-screen" aria-live="polite">
        <span className="brand-mark">R</span>
        <p>Loading RouteWise data…</p>
      </main>
    )
  }

  if (!metadata && !apiConnected) {
    return (
      <main className="connection-screen">
        <span className="brand-mark">R</span>
        <p className="eyebrow">ROUTEWISE SERVICE</p>
        <h1>Backend connection unavailable</h1>
        <p>{error || 'The dashboard needs the RouteWise API to load real shipment data.'}</p>
        <div className="connection-instructions">
          <strong>Start the backend from the project root in a separate terminal:</strong>
          <code>backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000</code>
          <span>Then retry. In a new checkout, install dependencies first using the README setup instructions.</span>
        </div>
        <button className="button button-primary" disabled={retrying} onClick={() => void refreshWorkspace()} type="button">
          {retrying ? 'Checking API…' : 'Retry connection'}
        </button>
      </main>
    )
  }

  return (
    <div className={`app-shell ${sidebarCompact ? 'sidebar-compact' : ''}`}>
      <aside className="sidebar">
        <a aria-label="RouteWise — Overview" className="brand" href="#overview" onClick={() => chooseSection('overview')}>
          <span className="brand-mark">R</span>
          <span className="brand-copy">
            <strong>RouteWise</strong>
            <small>LOGISTICS INTELLIGENCE</small>
          </span>
        </a>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation" className="side-nav">
          {[
            ['overview', 'Overview', '◫'],
            ['shipments', 'Shipments', '⇢'],
            ['decision-lab', 'Decision lab', '◈'],
            ['disruption-lab', 'Disruption lab', '⚡'],
            ['evaluation', 'Evaluation', '⌁'],
          ].map(([section, label, icon]) => (
            <button
              aria-current={activeSection === section ? 'page' : undefined}
              aria-label={label}
              className={`nav-link ${activeSection === section ? 'active' : ''}`}
              data-tooltip={label}
              title={label}
              key={section}
              onClick={() => chooseSection(section)}
              type="button"
            >
              <span aria-hidden="true" className="nav-icon">{icon}</span>
              <span className="nav-label">{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={`status-dot ${apiConnected ? '' : 'disconnected'}`} />
          <span>{apiConnected ? 'API connected' : 'API unavailable'}</span>
          <small>synthetic dataset</small>
        </div>
        <button
          className="sidebar-toggle"
          onClick={() => {
            setSidebarCompact((value) => !value)
            setToast(`Sidebar ${sidebarCompact ? 'expanded' : 'compacted'}.`)
          }}
          type="button"
          aria-label={sidebarCompact ? 'Expand sidebar' : 'Compact sidebar'}
          title={sidebarCompact ? 'Expand sidebar' : 'Compact sidebar'}
        >
          {sidebarCompact ? '»' : '«'}<span>Sidebar</span>
        </button>
      </aside>

      <main className="main-content" ref={mainContentRef}>
        <header className="topbar">
          <div>
            <p className="eyebrow">ROUTE PLANNING / {sectionNames[activeSection]?.toUpperCase() ?? 'ANALYTICS'}</p>
            <h1>Shipment intelligence</h1>
          </div>
          <div className="topbar-actions">
            <span aria-live="polite" className={`dataset-tag api-indicator ${apiConnected ? 'connected' : 'disconnected'}`} role="status" title="Connection status from the RouteWise API health check"><span className={`status-dot ${apiConnected ? '' : 'disconnected'}`} /> {apiConnected ? 'API connected' : 'API unavailable'}</span>
            <button className="icon-button" type="button" title="Search and navigate (Ctrl+K)" aria-label="Open command palette" onClick={() => setPaletteOpen(true)}>⌕ <kbd>Ctrl K</kbd></button>
            <button className="icon-button" type="button" title="Refresh server data" aria-label="Refresh data" onClick={() => void refreshWorkspace()}>↻</button>
            <button className="icon-button" type="button" title="Appearance and display settings" aria-label="Open settings" onClick={() => setSettingsOpen(true)}>⚙</button>
            <button aria-label="+ New Shipment" className="button button-primary new-shipment-action" onClick={openCreateShipment} title="Create a transient shipment" type="button">
              <span aria-hidden="true">+</span><span className="new-shipment-label">New Shipment</span>
            </button>
            <button
              className="button button-primary"
              disabled={!selectedShipmentId || !weightsValid || optimizing}
              onClick={() => void recalculate()}
              type="button"
            >
              {optimizing ? 'Optimizing…' : '↻  Optimize routes'}
            </button>
          </div>
        </header>

        {error && (
          <div className={`error-banner ${apiConnected ? '' : 'service-unavailable'}`} role="alert">
            <strong>Service notice</strong>
            <span>{error}</span>
            {!apiConnected && <span className="error-help">From the project root: <code>backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000</code></span>}
            <button className="text-button" disabled={retrying} type="button" onClick={() => void refreshWorkspace()}>{retrying ? 'Checking…' : 'Retry'}</button>
            {apiConnected && <button aria-label="Dismiss service notice" onClick={() => setError('')} type="button">×</button>}
          </div>
        )}

        <section className="hero-banner" id="overview">
          <div>
            <span className="hero-kicker">EXPLAINABLE SHIPMENT ROUTE OPTIMIZER</span>
            <h2>Make every route decision<br />with confidence.</h2>
            <p>Compare eligible routes across cost, speed, and risk—with every trade-off in view.</p>
            <button
              className="hero-link"
              onClick={() => chooseSection('decision-lab')}
              type="button"
            >
              Open decision lab <span aria-hidden="true">→</span>
            </button>
          </div>
          <div aria-hidden="true" className="hero-art">
            <span className="orbit orbit-one" />
            <span className="orbit orbit-two" />
            <span className="route-path path-one" />
            <span className="route-path path-two" />
            <span className="map-dot dot-one" />
            <span className="map-dot dot-two" />
            <span className="map-dot dot-three" />
            <span className="map-pin">✦</span>
            <span className="map-label label-one">ROTTERDAM</span>
            <span className="map-label label-two">SINGAPORE</span>
          </div>
        </section>

        <section aria-label="Dataset summary" className="stats-grid">
          <button className="stat-card clickable-stat" onClick={() => { setShipmentFilter('all'); chooseSection('shipments') }} type="button">
            <span className="stat-icon indigo">⇢</span>
            <span className="stat-label">Total shipments</span>
            <strong>{metadata?.shipment_count ?? 0}</strong>
            <small>Across synthetic lanes</small>
          </button>
          <button className="stat-card clickable-stat" onClick={() => { setShipmentFilter('all'); chooseSection('shipments') }} type="button">
            <span className="stat-icon teal">◇</span>
            <span className="stat-label">Candidate routes</span>
            <strong>{metadata?.route_count ?? 0}</strong>
            <small>Up to 4, where geography permits</small>
          </button>
          <button className="stat-card clickable-stat" onClick={() => { setShipmentFilter('feasible'); chooseSection('shipments') }} type="button">
            <span className="stat-icon green">✓</span>
            <span className="stat-label">Feasible routes</span>
            <strong>{metadata?.feasible_route_count ?? 0}</strong>
            <small>Pass all hard limits</small>
          </button>
          <button className="stat-card clickable-stat" onClick={() => { setShipmentFilter('no_feasible_route'); chooseSection('shipments') }} type="button">
            <span className="stat-icon amber">!</span>
            <span className="stat-label">No feasible options</span>
            <strong>{metadata?.shipments_without_feasible_routes ?? 0}</strong>
            <small>Need constraint review</small>
          </button>
        </section>

        <div className="content-grid overview-grid">
          <section className="panel" aria-labelledby="route-mix-title">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">NETWORK SNAPSHOT</p>
                <h2 id="route-mix-title">Candidate mix by mode</h2>
              </div>

              <span className="panel-note">Routes</span>
            </div>
            <div className="bar-chart">
                {Object.entries(metadata?.route_modes ?? {}).sort(([a], [b]) => a.localeCompare(b)).map(([mode, count], index) => (
                <div className="mode-bar-item" key={mode}>
                  <div className="mode-bar-meta">
                    <span>{mode}</span>
                    <strong>{count}</strong>
                  </div>
                  <div className="chart-track">
                    <span
                      className={`chart-bar mode-color-${index}`}
                      style={{ width: `${(count / maxModeCount) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <p className="chart-footnote">Even candidate coverage across available transport modes.</p>
          </section>
          <section className="panel" aria-labelledby="evaluation-snapshot-title">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">MEASURED BASELINES</p>
                <h2 id="evaluation-snapshot-title">Average outcome comparison</h2>
              </div>
              <button className="text-button" onClick={() => chooseSection('evaluation')} type="button">
                View evaluation →
              </button>
            </div>
            <div className="legend-row">
              <span><i className="legend-dot blue" />Weighted</span>
              <span><i className="legend-dot slate" />Cheapest</span>
              <span><i className="legend-dot teal" />Fastest</span>
              <span><i className="legend-dot violet" />Reliable</span>
            </div>
            <div className="mini-metric">
              <span>Average cost ({currencyDisplay}{currencyDisplay === 'USD' ? '' : ' · approx.'})</span>
              {evaluationEntries.map(([name, row]) => (
                <ChartBar
                  color={name === 'weighted_optimizer' ? 'blue' : name === 'cheapest_feasible' ? 'slate' : name === 'fastest_feasible' ? 'teal' : 'violet'}
                  key={name}
                  label={name.replace('_feasible', '').replace('_', ' ')}
                  max={costMax / 1000}
                  value={convertUsdForDisplay(row.average_cost_usd, currencyDisplay) / 1000}
                  suffix="k"
                />
              ))}
            </div>
          </section>
        </div>
        <div className="content-grid overview-grid">
          <section className="panel" aria-labelledby="activity-title">
            <div className="panel-heading">
              <div><p className="eyebrow">THIS SESSION</p><h2 id="activity-title">Recent activity</h2></div>
              <span className="panel-note">Not persisted</span>
            </div>
            {activity.length ? (
              <ul className="activity-list">
                {activity.slice(0, 5).map((item, index) => (
                  <li key={`${item.at}-${index}`}><span>{item.text}</span><time>{item.at}</time></li>
                ))}
              </ul>
            ) : <div className="empty-state">Optimization and simulation actions appear here for this session.</div>}
          </section>
          <section className="panel" aria-labelledby="scatter-title">
            <div className="panel-heading">
              <div><p className="eyebrow">SELECTED SHIPMENT · ACTUAL API VALUES</p><h2 id="scatter-title">Cost versus transit time</h2></div>
            </div>
            <RouteScatterChart
              displayCurrency={currencyDisplay}
              onSelect={setSelectedRouteId}
              recommendedRouteId={optimization?.recommendation?.route_id}
              routes={routeCandidates}
              selectedRouteId={selectedRouteId}
            />
            {routeCandidates.length > 0 && <p className="chart-footnote">Candidates and feasibility come from the selected shipment’s API result; display conversion does not change USD data.</p>}
          </section>
        </div>

        <section className="panel shipment-panel" id="shipments" aria-labelledby="shipments-title">
          <div className="panel-heading panel-heading-wrap">
            <div>
              <p className="eyebrow">SHIPMENT EXPLORER</p>
              <h2 id="shipments-title">Choose a shipment to compare routes</h2>
              <p className="panel-subtitle">Search by shipment ID, origin, destination, or cargo type. {shipmentFilter !== 'all' && `Showing ${shipmentFilter === 'feasible' ? 'feasible' : 'no-option'} shipments.`}</p>
            </div>
            <label className="search-box">
              <span aria-hidden="true">⌕</span>
              <span className="sr-only">Search shipments</span>
              <input
                aria-label="Search shipments"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search shipments…"
                type="search"
                value={search}
              />
              <kbd>/</kbd>
            </label>
            <div className="shipment-explorer-actions">
              <button className="button button-secondary shipment-create-action" onClick={openCreateShipment} type="button">Create Shipment</button>
              <button className="button button-secondary" onClick={() => exportCsv('routewise-shipments.csv', visibleShipments.map((shipment) => ({
                shipment_id: shipment.shipment_id, origin: shipment.origin, destination: shipment.destination,
                cargo_type: shipment.cargo_type, budget_usd: shipment.max_cost_usd,
                deadline_days: shipment.max_transit_days, computed_status: shipment.computed_status,
              })))} type="button">Export shipments</button>
            </div>
          </div>
          <div className="shipment-layout">
            <div className="shipment-list-wrap">
              <div className="table-scroll">
                <table className="data-table shipment-table">
                  <thead>
                    <tr>
                      <th><button className="sort-button" onClick={() => toggleShipmentSort('shipment_id')} type="button">Shipment {shipmentSort.key === 'shipment_id' ? (shipmentSort.descending ? '↓' : '↑') : '↕'}</button></th>
                      <th>Lane</th>
                      <th><button className="sort-button" onClick={() => toggleShipmentSort('max_cost_usd')} type="button">Budget {shipmentSort.key === 'max_cost_usd' ? (shipmentSort.descending ? '↓' : '↑') : '↕'}</button><button className="sort-button" onClick={() => toggleShipmentSort('max_transit_days')} type="button">Deadline {shipmentSort.key === 'max_transit_days' ? (shipmentSort.descending ? '↓' : '↑') : '↕'}</button></th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleShipments.map((shipment) => (
                      <tr
                        aria-selected={shipment.shipment_id === selectedShipmentId}
                        className={shipment.shipment_id === selectedShipmentId ? 'selected-row' : ''}
                        key={shipment.shipment_id}
                        onClick={() => {
                          chooseShipment(shipment.shipment_id)
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            chooseShipment(shipment.shipment_id)
                          }
                        }}
                        role="button"
                        tabIndex={0}
                      >
                        <td><strong>{shipment.shipment_id}</strong><small>{displayName(shipment.cargo_type)}</small></td>
                        <td>{shipment.origin}<span className="lane-arrow">→</span>{shipment.destination}</td>
                        <td>{currency(shipment.max_cost_usd, currencyDisplay)}<small>{shipment.max_transit_days.toFixed(1)} days</small></td>
                        <td>
                          <span className={`status-pill ${shipment.computed_status === 'feasible' ? 'good' : 'warning'}`}>
                            {shipment.computed_status === 'feasible' ? 'Feasible' : 'No options'}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {!visibleShipments.length && (
                      <tr><td className="empty-cell" colSpan={4}>No shipments match this search.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            {selectedShipment ? (
              <aside className="shipment-detail">
                <div className="detail-title-row">
                  <div>
                    <p className="eyebrow">SELECTED SHIPMENT</p>
                    <h3>{selectedShipment.shipment_id}</h3>
                  </div>
                  <span className={`status-pill ${selectedShipment.computed_status === 'feasible' ? 'good' : 'warning'}`}>
                    {selectedShipment.computed_status === 'feasible' ? 'Eligible routes' : 'No feasible route'}
                  </span>
                </div>
                <p className="detail-lane">{selectedShipment.origin}<span>→</span>{selectedShipment.destination}</p>
                <div className="detail-facts">
                  <div><small>CARGO WEIGHT</small><strong>{selectedShipment.weight_kg.toLocaleString()} kg</strong></div>
                  <div><small>{selectedIsCreated ? 'SYNTHETIC DISTANCE ESTIMATE' : 'LANE DISTANCE'}</small><strong>{selectedShipment.distance_km.toLocaleString()} km</strong></div>
                  <div><small>MAX BUDGET</small><strong>{currency(selectedShipment.max_cost_usd, currencyDisplay)}</strong></div>
                  <div><small>DEADLINE</small><strong>{selectedShipment.max_transit_days.toFixed(1)} days</strong></div>
                </div>
                <div className="risk-limit-list">
                  <span>Shipment risk limits</span>
                  <span>Delay cap <b>{percent(selectedShipment.max_delay_probability)}</b></span>
                  <span>Congestion cap <b>{percent(selectedShipment.max_congestion_risk)}</b></span>
                  <span>Geopolitical cap <b>{percent(selectedShipment.max_geopolitical_risk)}</b></span>
                </div>
              </aside>
            ) : (
              <div className="shipment-detail empty-state">Select a shipment to inspect its lane and constraints.</div>
            )}
          </div>
        </section>

        <section className="decision-layout" id="decision-lab">
          <div className="panel decision-controls">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">DECISION LAB</p>
                <h2>Set your priorities</h2>
              </div>
              <span aria-hidden="true" className="section-symbol">◈</span>
            </div>
            <label className="field-label" htmlFor="profile-select">Decision profile</label>
            <select
              className="form-control"
              id="profile-select"
              onChange={(event) => {
                if (event.target.value === 'custom') {
                  setProfile('custom')
                  return
                }
                chooseProfile(event.target.value as Profile)
              }}
              value={profile}
            >
              {Object.entries(profileNames).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
              <option value="custom">Custom weights</option>
            </select>
            <p className="field-help">
              {profile === 'custom' ? 'Tune each objective below. Weights must add to 1.' : profileDescriptions[profile]}
            </p>
            <div className="weight-fields">
              {([
                ['cost', 'Cost weight', 'blue'],
                ['time', 'Transit-time weight', 'teal'],
                ['risk', 'Risk weight', 'violet'],
              ] as const).map(([key, label, color]) => (
                <label className="weight-control" key={key}>
                  <span><i className={`weight-dot ${color}`} />{label}</span>
                  <input
                    aria-label={label}
                    max="1"
                    min="0"
                    onChange={(event) => changeWeight(key, event.target.value)}
                    step="0.05"
                    type="number"
                    value={weights[key]}
                  />
                </label>
              ))}
            </div>
            <div aria-live="polite" className={`weight-total ${weightsValid ? 'valid' : 'invalid'}`}>
              <span>Total weight</span>
              <strong>{weightTotal.toFixed(2)} / 1.00 {weightsValid ? '✓' : '— adjust weights'}</strong>
            </div>
            {!weightsValid && <p className="validation-hint">Set cost + time + risk to exactly 1.00 before optimizing.</p>}
            <div className="divider" />
            <div className="constraint-heading">
              <div>
                <h3>Constraint overrides</h3>
                <p>Optional stricter or relaxed limits for this run.</p>
              </div>
              <button className="text-button" onClick={() => setOverrides({})} type="button">Reset</button>
            </div>
            <div className="constraint-grid">
              {constraintFields.map(({ key, label, unit }) => {
                const current = selectedShipment?.[key as keyof Shipment]
                return (
                  <label className="constraint-input" key={key}>
                    <span>{label}</span>
                    <div>
                      <input
                        aria-label={label}
                        max={unit === '0–1' ? 1 : undefined}
                        min={unit === '0–1' ? 0 : 0.01}
                        onChange={(event) => changeConstraint(key, event.target.value)}
                        step={unit === '0–1' ? 0.05 : 'any'}
                        type="number"
                        value={overrides[key] ?? (typeof current === 'number' ? current : '')}
                      />
                      <small>{unit}</small>
                    </div>
                  </label>
                )
              })}
            </div>
            <button
              className="button button-primary optimize-full"
              disabled={!selectedShipmentId || !weightsValid || optimizing}
              onClick={() => void recalculate()}
              type="button"
            >
              {optimizing ? 'Recalculating…' : 'Optimize selected shipment'}
              <span aria-hidden="true">→</span>
            </button>
          </div>

          <div className="panel results-panel" aria-live="polite">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">ROUTE COMPARISON</p>
                <h2>{selectedShipment ? `${selectedShipment.shipment_id} recommendation` : 'Select a shipment'}</h2>
              </div>
              {optimization?.status === 'recommended' && (
                <span className="status-pill good">Best fit · {profile === 'custom' ? 'Custom' : profileNames[profile]}</span>
              )}
            </div>
            {selectedIsCreated && activeCreatedResult && (
              <div className="synthetic-shipment-notice" role="note">
                <strong>{activeCreatedResult.synthetic_estimates ? 'Illustrative synthetic estimates' : 'User-supplied candidate metrics'}</strong>
                <span>
                  {activeCreatedResult.synthetic_estimates
                    ? 'Route metrics are constructed from shipment limits using fixed mode factors and seeded risk variation; they are not carrier quotes, actual distances, or forecasts.'
                    : 'Candidate metrics were supplied with this request and are not independently verified.'}
                </span>
                <small>This shipment and result are in browser session memory only; they are not saved to the CSV or database and will be lost on refresh or restart.</small>
              </div>
            )}
            {optimizing && !optimization && <div className="loading-inline">Scoring eligible alternatives…</div>}
            {optimization && selectedShipment && (
              <RouteMap
                destination={selectedShipment.destination}
                onSelectRoute={setSelectedRouteId}
                origin={selectedShipment.origin}
                recommendedRouteId={optimization.recommendation?.route_id ?? null}
                routes={routeCandidates}
                selectedRouteId={selectedMapRoute?.route_id ?? null}
              />
            )}
            {optimization?.status === 'no_feasible_route' && (
              <div className="no-route-state" role="status">
                <span className="no-route-icon">!</span>
                <h3>No feasible route found</h3>
                <p>Every candidate violates an active hard constraint or transport-feasibility rule. No route has been recommended.</p>
                <ul>
                  {optimization.rejected_routes.map((route) => (
                    <li key={route.route_id}>
                      <strong>{route.route_id}</strong>
                      <span>{route.rejection_reasons?.join(' · ')}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {optimization?.recommendation && (
              <>
                <div className="recommendation-card">
                  <div className="recommendation-topline">
                    <span className="recommendation-tag"><span>✦</span> RECOMMENDED ROUTE</span>
                    <span className="rank-tag">RANK #{optimization.recommendation.rank}</span>
                  </div>
                  <div className="recommendation-main">
                    <div>
                      <h3>{optimization.recommendation.route_id}</h3>
                      <p>{displayName(optimization.recommendation.route_mode)} freight · {selectedShipment?.origin} → {selectedShipment?.destination}</p>
                    </div>
                    <strong className="score-value">{optimization.recommendation.total_penalty?.toFixed(4)}<small>objective</small></strong>
                  </div>
                  <div className="recommended-metrics">
                    <div><span>Total cost</span><strong>{currency(optimization.recommendation.cost_usd, currencyDisplay)}</strong></div>
                    <div><span>Transit time</span><strong>{optimization.recommendation.transit_time_days.toFixed(1)} days</strong></div>
                    <div><span>Delay probability</span><strong>{percent(optimization.recommendation.delay_probability)}</strong></div>
                    <div><span>Risk penalty</span><strong>{optimization.recommendation.risk_penalty?.toFixed(3)}</strong></div>
                  </div>
                  <p className="recommendation-explanation">{optimization.explanation}</p>
                  <div className="contribution-list">
                    <span className="contribution-title">Objective contribution</span>
                    {Object.entries(optimization.recommendation.weighted_contributions ?? {}).map(([name, value]) => (
                      <div key={name}>
                        <span>{name} · {optimization.weights[name as keyof WeightSet].toFixed(2)} weight</span>
                        <strong>{value.toFixed(4)}</strong>
                      </div>
                    ))}
                    <div className="contribution-total"><span>Total penalty</span><strong>{optimization.recommendation.total_penalty?.toFixed(4)}</strong></div>
                  </div>
                </div>
                <div className="route-tools">
                  <div className="compare-picker">
                    <label className="field-label" htmlFor="compare-route-select">Compare routes side by side</label>
                    <select
                      className="form-control"
                      id="compare-route-select"
                      onChange={(event) => {
                        const routeId = event.target.value
                        if (!routeId) return
                        setCompareRouteIds((current) =>
                          current.includes(routeId)
                            ? current.filter((item) => item !== routeId)
                            : current.length < 3 ? [...current, routeId] : [...current.slice(1), routeId],
                        )
                      }}
                      value=""
                    >
                      <option value="">Add a candidate (up to 3)</option>
                      {routeCandidates.map((route) => (
                        <option key={route.route_id} disabled={compareRouteIds.includes(route.route_id)} value={route.route_id}>
                          {route.route_id} · {route.feasibility_status}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    className="button button-secondary"
                    disabled={!routeCandidates.length}
                    onClick={() => exportCsv(`${selectedShipmentId}-routes.csv`, routeCandidates.map((route) => ({
                      route_id: route.route_id,
                      mode: route.route_mode,
                      feasible: route.is_feasible,
                      cost_usd: route.cost_usd,
                      transit_time_days: route.transit_time_days,
                      delay_probability: route.delay_probability,
                      congestion_risk: route.congestion_risk,
                      geopolitical_risk: route.geopolitical_risk,
                      total_penalty: route.total_penalty ?? '',
                    })))}
                    type="button"
                  >Export candidates</button>
                </div>
                {comparedRoutes.length > 0 && (
                  <div className="comparison-cards" aria-label="Selected route comparison">
                    {comparedRoutes.map((route) => (
                      <article className={`comparison-card ${route.is_feasible ? '' : 'is-infeasible'}`} key={route.route_id}>
                        <div><strong>{route.route_id}</strong><button aria-label={`Remove ${route.route_id} from comparison`} onClick={() => setCompareRouteIds((current) => current.filter((id) => id !== route.route_id))} type="button">×</button></div>
                        <span>{displayName(route.route_mode)} · {route.feasibility_status}</span>
                        <dl>
                          <div><dt>Cost</dt><dd>{currency(route.cost_usd, currencyDisplay)}</dd></div>
                          <div><dt>Transit</dt><dd>{route.transit_time_days.toFixed(1)} days</dd></div>
                          <div><dt>Delay</dt><dd>{percent(route.delay_probability)}</dd></div>
                          <div><dt>Congestion</dt><dd>{percent(route.congestion_risk)}</dd></div>
                          <div><dt>Geopolitical</dt><dd>{percent(route.geopolitical_risk)}</dd></div>
                          <div><dt>Objective</dt><dd>{route.total_penalty?.toFixed(4) ?? 'Excluded'}</dd></div>
                        </dl>
                        {!route.is_feasible && <p>{route.rejection_reasons?.join(' · ')}</p>}
                        {route.explanation && <p>{route.explanation}</p>}
                      </article>
                    ))}
                  </div>
                )}
                {selectedRoute && (
                  <div className="route-inspector" role="region" aria-label={`${selectedRoute.route_id} route details`}>
                    <div><strong>{selectedRoute.route_id} details</strong><button className="text-button" onClick={() => setSelectedRouteId('')} type="button">Close</button></div>
                    <p>{selectedRoute.explanation ?? selectedRoute.rejection_reasons?.join(' · ') ?? 'Candidate route details.'}</p>
                    <span>{selectedRoute.is_feasible ? `Eligible · penalty ${selectedRoute.total_penalty?.toFixed(4)}` : `Ineligible · ${selectedRoute.rejection_reasons?.join('; ')}`}</span>
                  </div>
                )}
                <div className="rejection-note">
                  <strong>Why alternatives ranked lower</strong>
                  <p>All listed alternatives passed active constraints. Their deterministic ranks reflect the displayed normalized cost, time, and risk contributions.</p>
                </div>
                {optimization.warnings.length > 0 && (
                  <div className="warning-list">
                    {optimization.warnings.map((warning) => <p key={warning}>{warning}</p>)}
                  </div>
                )}
              </>
            )}
            {optimization && (
              <section aria-label="Candidate routes and actual metrics" className="table-scroll route-table-wrap">
                <table className="data-table route-table">
                  <thead>
                    <tr><th>Candidate</th><th>Eligibility / rejection reason</th><th>Cost</th><th>Days</th><th>Delay</th><th>Congestion</th><th>Geo risk</th><th>Penalty</th></tr>
                  </thead>
                  <tbody>
                    {routeCandidates.map((route) => (
                      <tr className={route.is_feasible ? route.rank === 1 ? 'winner-row' : '' : 'infeasible-row'} key={route.route_id}>
                        <td>
                          <button className="route-select-button" onClick={() => setSelectedRouteId(route.route_id)} type="button" aria-label={`Inspect ${route.route_id}`}>
                            <strong>{route.route_id}</strong><small>{displayName(route.route_mode)}</small>
                          </button>
                        </td>
                        <td>
                          {route.is_feasible
                            ? `Eligible · rank #${route.rank}`
                            : route.rejection_reasons?.join('; ') || 'Ineligible'}
                        </td>
                        <td>{currency(route.cost_usd, currencyDisplay)}</td>
                        <td>{route.transit_time_days.toFixed(1)}</td>
                        <td>{percent(route.delay_probability)}</td>
                        <td>{percent(route.congestion_risk)}</td>
                        <td>{percent(route.geopolitical_risk)}</td>
                        <td>{route.total_penalty === null || route.total_penalty === undefined
                          ? <span className="status-pill muted">Excluded</span>
                          : <strong>{route.total_penalty.toFixed(4)}</strong>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
            {!selectedShipment && <div className="empty-state">Select a shipment from the explorer to see its recommendation.</div>}
            {!selectedIsCreated && <section className="analyst-panel" aria-labelledby="analyst-title">
              <div className="analyst-heading">
                <div>
                  <p className="eyebrow">OPTIONAL GROQ COMMENTARY</p>
                  <h3 id="analyst-title">AI Logistics Analyst</h3>
                </div>
                <button
                  className="button button-secondary"
                  disabled={!optimization || optimizing || analystLoading || !weightsValid}
                  onClick={() => void requestAnalystExplanation()}
                  type="button"
                >
                  {analystLoading
                    ? 'Generating…'
                    : analystExplanation
                      ? 'Refresh explanation'
                      : 'Generate explanation'}
                </button>
              </div>
              <p className="analyst-disclaimer">
                Optional decision support only. Route metrics below are computed by the optimizer; generated commentary does not rank routes or change constraints.
              </p>
              {analystLoading && <p className="loading-inline" role="status">Preparing an explanation from the current optimizer result…</p>}
              {analystError && <p className="form-error" role="alert">{analystError}</p>}
              {analystExplanation && (
                <div className="analyst-result" aria-live="polite">
                  <span className="status-pill muted">
                    {analystExplanation.source === 'groq'
                      ? `AI-generated · ${analystExplanation.model ?? 'Groq'}`
                      : analystExplanation.provider_status === 'not_applicable'
                        ? 'Deterministic · no feasible route'
                        : 'Deterministic fallback'}
                  </span>
                  {analystExplanation.computed_facts.selected_route_id ? (
                    <div className="analyst-facts" aria-label="Optimizer-computed route facts">
                      <span><strong>Route:</strong> {analystExplanation.computed_facts.selected_route_id} · {displayName(analystExplanation.computed_facts.selected_route_mode ?? '')}</span>
                      <span><strong>Cost:</strong> {currency(analystExplanation.computed_facts.cost_usd ?? 0, currencyDisplay)}</span>
                      <span><strong>Transit:</strong> {analystExplanation.computed_facts.transit_time_days?.toFixed(1)} days</span>
                      <span><strong>Delay:</strong> {percent(analystExplanation.computed_facts.delay_probability ?? 0)}</span>
                      <span><strong>Congestion:</strong> {percent(analystExplanation.computed_facts.congestion_risk ?? 0)}</span>
                      <span><strong>Geopolitical risk:</strong> {percent(analystExplanation.computed_facts.geopolitical_risk ?? 0)}</span>
                      <span><strong>Risk penalty:</strong> {analystExplanation.computed_facts.risk_penalty?.toFixed(3)}</span>
                      <span><strong>Objective:</strong> {analystExplanation.computed_facts.total_penalty?.toFixed(4)}</span>
                    </div>
                  ) : (
                    <p className="analyst-disclaimer">No route was selected. {analystExplanation.computed_facts.rejected_route_count} candidates were rejected by the current hard constraints.</p>
                  )}
                  {analystExplanation.computed_facts.weights && (
                    <p className="analyst-disclaimer">
                      Active weights · Cost {analystExplanation.computed_facts.weights.cost.toFixed(2)} · Time {analystExplanation.computed_facts.weights.time.toFixed(2)} · Risk {analystExplanation.computed_facts.weights.risk.toFixed(2)}
                    </p>
                  )}
                  {Object.keys(analystExplanation.computed_facts.constraints).length > 0 && (
                    <div className="analyst-facts" aria-label="Optimizer hard constraints">
                      {Object.entries(analystExplanation.computed_facts.constraints).map(([key, value]) => (
                        <span key={key}>
                          <strong>{displayName(key.replace(/^max_/, '').replace(/_usd$/, ''))} limit:</strong>{' '}
                          {key === 'max_cost_usd'
                            ? currency(value, currencyDisplay)
                            : key.endsWith('_days')
                              ? `${value} days`
                              : percent(value)}
                        </span>
                      ))}
                    </div>
                  )}
                  {(analystExplanation.computed_facts.cheapest_feasible || analystExplanation.computed_facts.fastest_feasible) && (
                    <div className="analyst-facts" aria-label="Optimizer-computed alternatives">
                      {analystExplanation.computed_facts.cheapest_feasible && (
                        <span><strong>Cheapest feasible:</strong> {analystExplanation.computed_facts.cheapest_feasible.route_id} · {currency(analystExplanation.computed_facts.cheapest_feasible.cost_usd, currencyDisplay)} · {analystExplanation.computed_facts.cheapest_feasible.transit_time_days.toFixed(1)} days</span>
                      )}
                      {analystExplanation.computed_facts.fastest_feasible && (
                        <span><strong>Fastest feasible:</strong> {analystExplanation.computed_facts.fastest_feasible.route_id} · {currency(analystExplanation.computed_facts.fastest_feasible.cost_usd, currencyDisplay)} · {analystExplanation.computed_facts.fastest_feasible.transit_time_days.toFixed(1)} days</span>
                      )}
                    </div>
                  )}
                  <div className="analyst-narrative">
                    <p>{analystExplanation.narrative.summary}</p>
                    <h4>Trade-offs</h4>
                    <ul>{analystExplanation.narrative.tradeoffs.map((item, index) => <li key={`tradeoff-${index}`}>{item}</li>)}</ul>
                    <h4>Constraints applied</h4>
                    <ul>{analystExplanation.narrative.constraint_notes.map((item, index) => <li key={`constraint-${index}`}>{item}</li>)}</ul>
                    <h4>Uncertainty</h4>
                    <ul>{analystExplanation.narrative.uncertainties.map((item, index) => <li key={`uncertainty-${index}`}>{item}</li>)}</ul>
                  </div>
                  {analystExplanation.warning && <p className="analyst-warning" role="status">{analystExplanation.warning}</p>}
                  <p className="analyst-disclaimer">AI-generated decision support is not a verified prediction. Review the computed values and assumptions independently.</p>
                </div>
              )}
            </section>}
          </div>
        </section>

        <section className="panel sensitivity-panel" aria-labelledby="sensitivity-title">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">WEIGHT SENSITIVITY</p>
              <h2 id="sensitivity-title">How priorities shift the recommendation</h2>
            </div>
            {sensitivity && <span className="stability-badge">{percent(sensitivity.recommendation_stability)} stable</span>}
          </div>
          <p className="panel-subtitle">
            Live API results for profile presets and additional cost- and risk-heavy weight combinations.
          </p>
          {sensitivityLoading && <div className="loading-inline">Testing weight combinations…</div>}
          {!sensitivityLoading && sensitivity && (
            <div className="sensitivity-content">
              <div className="sensitivity-chart">
                {sensitivity.points.map((point, index) => (
                  <div className="sensitivity-point" key={`${point.selected_route_id ?? 'none'}-${index}`}>
                    <div className="sensitivity-meta">
                      <span>Set {index + 1}</span>
                      <strong>{point.selected_route_id ?? 'No feasible route'}</strong>
                    </div>
                    <span className="sensitivity-track">
                      <i style={{ width: `${Math.max(5, (point.total_penalty ?? 0) * 100)}%` }} />
                    </span>
                    <small>C {point.weights.cost.toFixed(2)} · T {point.weights.time.toFixed(2)} · R {point.weights.risk.toFixed(2)}</small>
                  </div>
                ))}
              </div>
              <aside className="sensitivity-summary">
                <span className="eyebrow">STABILITY CHECK</span>
                <strong>{sensitivity.route_changes_between_adjacent_points}</strong>
                <span>recommendation changes between adjacent weight sets</span>
                <p>{sensitivity.explanation}</p>
                <div className="recommendation-counts">
                  {Object.entries(sensitivity.recommendation_counts).map(([routeId, count]) => (
                    <span key={routeId}>{routeId}<b>{count}</b></span>
                  ))}
                </div>
              </aside>
            </div>
          )}
          {!sensitivityLoading && !sensitivity && (
            <div className="empty-state">Choose a shipment to calculate weight sensitivity.</div>
          )}
        </section>

        <section className="disruption-section" id="disruption-lab" aria-labelledby="disruption-title">
          <div className="panel disruption-controls">
            <div className="panel-heading">
              <div><p className="eyebrow">WHAT-IF ANALYSIS</p><h2 id="disruption-title">Disruption Lab</h2></div>
              <span className="section-symbol">⚡</span>
            </div>
            <p className="panel-subtitle">Apply hypothetical metric shocks to copied route data. Original CSVs and routes are never modified.</p>
            {disruptionScenarios.map((scenario, index) => (
              <fieldset className="scenario-editor" key={scenario.name}>
                <legend>{scenario.name}</legend>
                {([
                  ['delay_probability_increase', 'Delay probability increase'],
                  ['congestion_risk_increase', 'Congestion risk increase'],
                  ['geopolitical_risk_increase', 'Geopolitical risk increase'],
                ] as const).map(([key, label]) => (
                  <label className="scenario-field" key={key}>
                    <span>{label} <b>+{percent(scenario[key])}</b></span>
                    <input aria-label={`${scenario.name} ${label}`} max="1" min="0" onChange={(event) => updateScenario(index, { [key]: Number(event.target.value) })} step="0.05" type="range" value={scenario[key]} />
                  </label>
                ))}
                {([
                  ['transit_time_increase_pct', 'Transit-time increase', 5],
                  ['cost_increase_pct', 'Cost increase', 5],
                ] as const).map(([key, label, max]) => (
                  <label className="scenario-field" key={key}>
                    <span>{label} <b>+{(scenario[key] * 100).toFixed(0)}%</b></span>
                    <input aria-label={`${scenario.name} ${label}`} max={max} min="0" onChange={(event) => updateScenario(index, { [key]: Number(event.target.value) / 100 })} step="5" type="range" value={scenario[key] * 100} />
                  </label>
                ))}
                <label className="scenario-field">
                  <span>Affected route mode</span>
                  <select aria-label={`${scenario.name} affected route mode`} className="form-control" onChange={(event) => updateScenario(index, { route_modes: event.target.value ? [event.target.value] : [] })} value={scenario.route_modes[0] ?? ''}>
                    <option value="">All modes</option>
                    {['air', 'ocean', 'rail', 'road'].map((mode) => <option key={mode} value={mode}>{displayName(mode)}</option>)}
                  </select>
                </label>
                <label className="scenario-field">
                  <span>Affected candidate route (optional)</span>
                  <select
                    aria-label={`${scenario.name} affected route IDs`}
                    className="form-control"
                    multiple
                    onChange={(event) =>
                      updateScenario(index, {
                        route_ids: Array.from(
                          event.target.selectedOptions,
                          (option) => option.value,
                        ),
                      })
                    }
                    size={Math.min(4, Math.max(2, routeCandidates.length))}
                  >
                    {routeCandidates.map((route) => <option key={route.route_id} value={route.route_id}>{route.route_id} · {displayName(route.route_mode)}</option>)}
                  </select>
                  <small>When both mode and route are selected, both conditions must match.</small>
                </label>
              </fieldset>
            ))}
            <button className="button button-primary optimize-full" disabled={!selectedShipmentId || !weightsValid || simulating} onClick={() => void runDisruptionSimulation()} type="button">
              {simulating ? 'Simulating…' : 'Run hypothetical simulation'} <span aria-hidden="true">→</span>
            </button>
            {simulationError && <p className="form-error" role="alert">{simulationError}</p>}
          </div>
          <div className="panel disruption-results" aria-live="polite">
            <div className="panel-heading"><div><p className="eyebrow">SIMULATION OUTPUT</p><h2>Resilience comparison</h2></div>
              {disruptionResult && <button className="button button-secondary" onClick={() => exportCsv(`${selectedShipmentId}-disruption.csv`, disruptionResult.scenarios.flatMap((scenario) => scenario.routes.map((route) => ({
                scenario: scenario.name, route_id: route.route_id, baseline_feasible: route.baseline_feasible,
                disrupted_feasible: route.disrupted_feasible, baseline_cost_usd: route.baseline_metrics.cost_usd,
                disrupted_cost_usd: route.disrupted_metrics.cost_usd, baseline_transit_days: route.baseline_metrics.transit_time_days,
                disrupted_transit_days: route.disrupted_metrics.transit_time_days,
              }))))} type="button">Export simulation</button>}
            </div>
            {!disruptionResult && !simulating && <div className="empty-state">Configure the hypothetical shocks and run the simulation to compare reoptimized outcomes.</div>}
            {simulating && <div className="loading-inline">Transforming candidate copies and rechecking constraints…</div>}
            {disruptionResult && (
              <>
                <p className="simulation-warning">Hypothetical scenario only. Changes are deterministic and illustrative, not forecasts.</p>
                <p className="baseline-summary">Baseline recommendation: <strong>{disruptionResult.baseline.recommendation?.route_id ?? 'No feasible route'}</strong> · {disruptionResult.baseline.feasible_candidate_count} of {disruptionResult.baseline.candidate_count} candidates feasible.</p>
                <div className="simulation-tabs" role="tablist" aria-label="Disruption scenarios">
                  {disruptionResult.scenarios.map((scenario, index) => <button aria-selected={selectedSimulationIndex === index} className={selectedSimulationIndex === index ? 'active' : ''} key={scenario.name} onClick={() => setSelectedSimulationIndex(index)} role="tab" type="button">{scenario.name}</button>)}
                </div>
                {disruptionResult.scenarios[selectedSimulationIndex] && (() => {
                  const scenario = disruptionResult.scenarios[selectedSimulationIndex]
                  return <>
                    <p>{scenario.summary}</p>
                    <div className="simulation-kpis">
                      <div><small>FEASIBLE CANDIDATES</small><strong>{scenario.comparison.feasible_candidate_count}/{scenario.routes.length}</strong></div>
                      <div><small>FEASIBILITY CHANGE</small><strong>{scenario.comparison.feasible_candidate_change > 0 ? '+' : ''}{scenario.comparison.feasible_candidate_change}</strong></div>
                      <div><small>RECOMMENDATION</small><strong>{scenario.recommendation?.route_id ?? 'None'}</strong></div>
                      <div><small>RECOMMENDATION CHANGE</small><strong>{scenario.comparison.recommendation_changed ? 'Changed' : 'Stable'}</strong></div>
                      <div><small>SELECTED COST DELTA</small><strong>{scenario.comparison.recommended_cost_change_usd === null ? 'N/A' : currency(scenario.comparison.recommended_cost_change_usd, currencyDisplay)}</strong></div>
                      <div><small>FALLBACK</small><strong>{scenario.comparison.fallback_available ? 'Available' : 'Unavailable'}</strong></div>
                    </div>
                    {!scenario.recommendation && <div className="no-route-state" role="status"><h3>No feasible route after disruption</h3><p>All candidates were rechecked against current hard constraints. No fallback is recommended.</p></div>}
                    <div className="table-scroll"><table className="data-table">
                      <thead><tr><th>Route</th><th>Mode</th><th>Baseline</th><th>Disrupted</th><th>Cost change</th><th>Transit change</th><th>Status</th></tr></thead>
                      <tbody>{scenario.routes.map((route) => <tr className={route.disrupted_feasible ? '' : 'infeasible-row'} key={route.route_id}>
                        <td>{route.route_id}</td><td>{displayName(route.route_mode)}</td><td>{route.baseline_feasible ? 'Eligible' : 'Ineligible'}</td><td>{route.disrupted_feasible ? 'Eligible' : 'Ineligible'}</td>
                        <td>{currency(route.disrupted_metrics.cost_usd - route.baseline_metrics.cost_usd, currencyDisplay)}</td><td>{(route.disrupted_metrics.transit_time_days - route.baseline_metrics.transit_time_days).toFixed(2)} d</td>
                        <td>{route.disrupted_rejection_reasons.join(' · ') || 'Passes constraints'}</td>
                      </tr>)}</tbody>
                    </table></div>
                  </>
                })()}
                <details className="assumption-details"><summary>Simulation assumptions</summary><ul>{disruptionResult.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></details>
              </>
            )}
          </div>
        </section>

        <section className="panel evaluation-panel" id="evaluation" aria-labelledby="evaluation-title">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">EVALUATION / SYNTHETIC DATA</p>
              <h2 id="evaluation-title">Measured strategy trade-offs</h2>
              <p className="panel-subtitle">{evaluation?.interpretation}</p>
            </div>
            <span className="synthetic-stamp">NOT REAL-WORLD PERFORMANCE</span>
          </div>
          <div className="table-scroll">
            <table className="data-table evaluation-table">
              <thead>
                <tr>
                  <th>Strategy</th><th>Selected</th><th>Feasibility rate</th><th>Avg. cost</th>
                  <th>Avg. transit</th><th>Avg. risk</th><th>Avg. objective</th><th>Violations</th>
                </tr>
              </thead>
              <tbody>
                {evaluationEntries.map(([name, result]) => (
                  <tr key={name}>
                    <td><strong>{displayName(name)}</strong></td>
                    <td>{result.count}</td>
                    <td>{percent(result.feasibility_rate)}</td>
                    <td>{currency(result.average_cost_usd, currencyDisplay)}</td>
                    <td>{result.average_transit_days.toFixed(2)} d</td>
                    <td>{result.average_risk_penalty.toFixed(4)}</td>
                    <td>{result.average_total_penalty.toFixed(4)}</td>
                    <td><span className={`status-pill ${result.constraint_violations === 0 ? 'good' : 'warning'}`}>{result.constraint_violations}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {evaluation && (
            <div className="evaluation-charts">
              <div className="evaluation-chart">
                <h3>Mean transit time <small>days · lower is better</small></h3>
                {evaluationEntries.map(([name, result]) => (
                  <ChartBar
                    color={name === 'weighted_optimizer' ? 'blue' : name === 'cheapest_feasible' ? 'slate' : name === 'fastest_feasible' ? 'teal' : 'violet'}
                    key={name}
                    label={displayName(name)}
                    max={timeMax}
                    value={result.average_transit_days}
                  />
                ))}
              </div>
              <div className="evaluation-chart">
                <h3>Mean risk penalty <small>0–1 · lower is better</small></h3>
                {evaluationEntries.map(([name, result]) => (
                  <ChartBar
                    color={name === 'weighted_optimizer' ? 'blue' : name === 'cheapest_feasible' ? 'slate' : name === 'fastest_feasible' ? 'teal' : 'violet'}
                    key={name}
                    label={displayName(name)}
                    max={riskMax}
                    value={result.average_risk_penalty}
                  />
                ))}
              </div>
            </div>
          )}
          <div className="evaluation-foot">
            <div><strong>Pareto frontier</strong><span>{evaluation?.pareto_frontier.non_dominated_route_count ?? 0} non-dominated routes from {evaluation?.pareto_frontier.eligible_route_count ?? 0} feasible options</span></div>
            <div><strong>Average frontier size</strong><span>{evaluation?.pareto_frontier.average_frontier_size_per_feasible_shipment ?? 0} options per feasible shipment</span></div>
            <div><strong>Profile sensitivity</strong><span>Recommendations are independently computed for all four profiles.</span></div>
          </div>
        </section>

        <footer className="page-footer">
          <span>RouteWise <b>·</b> Explainable Shipment Route Optimizer</span>
          <span>Synthetic candidate data · Illustrative assumptions only · No predictive claims</span>
        </footer>
        {settingsOpen && (
          <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false) }}>
            <section aria-labelledby="settings-title" aria-modal="true" className="settings-dialog" role="dialog">
              <div className="dialog-heading"><div><p className="eyebrow">PREFERENCES</p><h2 id="settings-title">Display settings</h2></div><button aria-label="Close settings" className="icon-button" onClick={() => setSettingsOpen(false)} type="button">×</button></div>
              <label className="settings-row" htmlFor="theme-setting"><span><strong>Theme</strong><small>Follow the device setting or choose a fixed theme.</small></span><select aria-label="Theme" className="form-control" id="theme-setting" onChange={(event) => setTheme(event.target.value as Theme)} value={theme}><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
              <label className="settings-row" htmlFor="density-setting"><span><strong>Layout density</strong><small>Compact rows reduce table and card spacing.</small></span><select aria-label="Layout density" className="form-control" id="density-setting" onChange={(event) => setDensity(event.target.value as Density)} value={density}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>
              <label className="settings-row" htmlFor="currency-setting"><span><strong>Currency display</strong><small>USD is canonical. EUR, GBP and INR use fixed approximate display-only rates; INR is 83.5 per USD.</small></span><select aria-label="Currency display" className="form-control" id="currency-setting" onChange={(event) => setCurrencyDisplay(event.target.value as DisplayCurrency)} value={currencyDisplay}><option value="USD">USD</option><option value="EUR">EUR (approx.)</option><option value="GBP">GBP (approx.)</option><option value="INR">INR (approx.)</option></select></label>
              <label className="settings-toggle"><span><strong>Reduce motion</strong><small>Disable non-essential interface transitions.</small></span><input checked={reducedMotion} onChange={(event) => setReducedMotion(event.target.checked)} type="checkbox" /></label>
              <label className="settings-toggle"><span><strong>Compact sidebar</strong><small>Show navigation icons with hover labels.</small></span><input checked={sidebarCompact} onChange={(event) => setSidebarCompact(event.target.checked)} type="checkbox" /></label>
              <p className="dialog-footnote">Preferences are stored in this browser only. Currency changes do not alter optimizer inputs or results.</p>
            </section>
          </div>
        )}
        {createShipmentOpen && (
          <div
            className="modal-backdrop create-shipment-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !creatingShipment) setCreateShipmentOpen(false)
            }}
          >
            <section
              aria-labelledby="create-shipment-title"
              aria-modal="true"
              className="settings-dialog create-shipment-dialog"
              role="dialog"
            >
              <div className="dialog-heading">
                <div>
                  <p className="eyebrow">TRANSIENT SHIPMENT</p>
                  <h2 id="create-shipment-title">Create Shipment</h2>
                </div>
                <button
                  aria-label="Close Create Shipment"
                  className="icon-button"
                  disabled={creatingShipment}
                  onClick={() => setCreateShipmentOpen(false)}
                  type="button"
                >×</button>
              </div>
              <p className="dialog-footnote">
                Required lane and constraint fields generate four reproducible illustrative routes. No carrier quotes or real distance data are used. Shipment and results are not saved to CSV or a database; they last only until this page is refreshed.
              </p>
              <form className="create-shipment-form" onSubmit={(event) => void createShipment(event)}>
                <div className="create-shipment-grid">
                  <label className="constraint-input">
                    <span>Origin</span>
                    <input autoComplete="off" maxLength={120} onChange={(event) => updateNewShipmentForm('origin', event.target.value)} required value={newShipmentForm.origin} />
                  </label>
                  <label className="constraint-input">
                    <span>Destination</span>
                    <input autoComplete="off" maxLength={120} onChange={(event) => updateNewShipmentForm('destination', event.target.value)} required value={newShipmentForm.destination} />
                  </label>
                  <label className="constraint-input">
                    <span>Cargo type</span>
                    <select onChange={(event) => updateNewShipmentForm('cargo_type', event.target.value)} required value={newShipmentForm.cargo_type}>
                      <option value="">Choose cargo type</option>
                      {['electronics', 'food', 'textiles', 'medical_supplies', 'machinery', 'chemicals'].map((cargo) => <option key={cargo} value={cargo}>{displayName(cargo)}</option>)}
                    </select>
                  </label>
                  <label className="constraint-input">
                    <span>Cargo weight</span>
                    <div><input aria-label="Cargo weight" max="1000000000" min="0.01" onChange={(event) => updateNewShipmentForm('weight_kg', event.target.value)} required step="any" type="number" value={newShipmentForm.weight_kg} /><small>kg</small></div>
                  </label>
                  <label className="constraint-input">
                    <span>Maximum budget</span>
                    <div><input aria-label="Maximum budget" max="1000000000" min="0.01" onChange={(event) => updateNewShipmentForm('max_cost_usd', event.target.value)} required step="any" type="number" value={newShipmentForm.max_cost_usd} /><small>USD</small></div>
                  </label>
                  <label className="constraint-input">
                    <span>Delivery deadline</span>
                    <div><input aria-label="Delivery deadline" max="100000" min="0.01" onChange={(event) => updateNewShipmentForm('max_transit_days', event.target.value)} required step="any" type="number" value={newShipmentForm.max_transit_days} /><small>days</small></div>
                  </label>
                  {([
                    ['max_delay_probability', 'Maximum delay probability'],
                    ['max_congestion_risk', 'Maximum congestion risk'],
                    ['max_geopolitical_risk', 'Maximum geopolitical risk'],
                  ] as const).map(([field, label]) => (
                    <label className="constraint-input" key={field}>
                      <span>{label}</span>
                      <div><input aria-label={label} max="1" min="0" onChange={(event) => updateNewShipmentForm(field, event.target.value)} required step="0.01" type="number" value={newShipmentForm[field]} /><small>0–1</small></div>
                    </label>
                  ))}
                </div>
                {createShipmentError && <p className="form-error" role="alert">{createShipmentError}</p>}
                <div className="create-shipment-actions">
                  <button className="button button-secondary" disabled={creatingShipment} onClick={() => setCreateShipmentOpen(false)} type="button">Cancel</button>
                  <button className="button button-primary" disabled={creatingShipment || !weightsValid} type="submit">
                    {creatingShipment ? 'Creating and optimizing…' : 'Create and optimize'}
                  </button>
                </div>
              </form>
            </section>
          </div>
        )}
        {paletteOpen && (
          <div className="modal-backdrop palette-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setPaletteOpen(false) }}>
            <section aria-label="Command palette" aria-modal="true" className="command-dialog" role="dialog">
              <label className="command-search"><span aria-hidden="true">⌕</span><input aria-label="Search commands and shipments" onChange={(event) => setPaletteQuery(event.target.value)} placeholder="Navigate or find a shipment…" ref={commandInput} value={paletteQuery} /><kbd>ESC</kbd></label>
              <div className="command-list">
                <p className="eyebrow">NAVIGATION</p>
                {Object.entries(sectionNames).map(([section, label]) => <button key={section} onClick={() => chooseSection(section)} type="button"><span>{label}</span><kbd>Go to section</kbd></button>)}
                {paletteShipments.length > 0 && <p className="eyebrow">SHIPMENTS</p>}
                {paletteShipments.map((shipment) => <button key={shipment.shipment_id} onClick={() => selectCommandShipment(shipment.shipment_id)} type="button"><span><strong>{shipment.shipment_id}</strong> · {shipment.origin} → {shipment.destination}</span><kbd>Select</kbd></button>)}
                {paletteQuery && paletteShipments.length === 0 && <p className="empty-state">No matching shipments.</p>}
              </div>
            </section>
          </div>
        )}
        {toast && <div aria-live="polite" className="toast-message" role="status">{toast}<button aria-label="Dismiss notification" onClick={() => setToast('')} type="button">×</button></div>}
      </main>
    </div>
  )
}

export default App
