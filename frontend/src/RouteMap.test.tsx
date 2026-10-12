import { useState } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouteMap } from './RouteMap'
import { resolveMapCoordinate } from './routeCoordinates'
import type { RouteCandidate } from './types'

vi.mock('react-leaflet', () => ({
  CircleMarker: ({ children }: { children?: import('react').ReactNode }) => children,
  MapContainer: ({ children }: { children?: import('react').ReactNode }) => children,
  Polyline: () => null,
  TileLayer: ({ eventHandlers }: { eventHandlers: { tileerror: () => void } }) => (
    <button onClick={eventHandlers.tileerror} type="button">Simulate tile error</button>
  ),
  Tooltip: ({ children }: { children?: import('react').ReactNode }) => children,
  useMap: () => ({ fitBounds: vi.fn(), invalidateSize: vi.fn() }),
}))

afterEach(cleanup)

const candidates: RouteCandidate[] = [
  {
    route_id: 'R-AIR',
    shipment_id: 'S1',
    route_mode: 'air',
    cost_usd: 1200,
    transit_time_days: 2,
    delay_probability: 0.1,
    congestion_risk: 0.2,
    geopolitical_risk: 0.1,
    stored_is_feasible: true,
    is_feasible: true,
    feasibility_status: 'feasible',
  },
  {
    route_id: 'R-OCEAN',
    shipment_id: 'S1',
    route_mode: 'ocean',
    cost_usd: 800,
    transit_time_days: 12,
    delay_probability: 0.2,
    congestion_risk: 0.3,
    geopolitical_risk: 0.2,
    stored_is_feasible: true,
    is_feasible: true,
    feasibility_status: 'feasible',
  },
  {
    route_id: 'R-REJECTED',
    shipment_id: 'S1',
    route_mode: 'road',
    cost_usd: 100,
    transit_time_days: 4,
    delay_probability: 0.1,
    congestion_risk: 0.1,
    geopolitical_risk: 0.1,
    stored_is_feasible: false,
    is_feasible: false,
    feasibility_status: 'infeasible',
    rejection_reasons: ['geographic infeasibility'],
  },
]

function RouteMapHarness() {
  const [selectedRouteId, setSelectedRouteId] = useState('R-AIR')
  return (
    <RouteMap
      destination="Singapore"
      onSelectRoute={setSelectedRouteId}
      origin="Hamburg, Germany"
      recommendedRouteId="R-AIR"
      routes={candidates}
      selectedRouteId={selectedRouteId}
    />
  )
}

describe('RouteMap', () => {
  it('resolves only cities from the offline geography catalog', () => {
    expect(resolveMapCoordinate('Hamburg, DE')).toEqual([53.5511, 9.9937])
    expect(resolveMapCoordinate('Tokyo, Japan')).toEqual([35.6762, 139.6503])
    expect(resolveMapCoordinate('Hamburg, Brazil')).toBeNull()
    expect(resolveMapCoordinate('Unlisted City, ZZ')).toBeNull()
  })

  it('updates the displayed candidate when another eligible route is selected', () => {
    render(<RouteMapHarness />)
    expect(screen.getByText('R-AIR · air · eligible')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Display eligible candidate on map'), {
      target: { value: 'R-OCEAN' },
    })

    expect(screen.getByText('R-OCEAN · ocean · eligible')).toBeInTheDocument()
    expect(screen.getByLabelText('Display eligible candidate on map')).toHaveValue('R-OCEAN')
    expect(screen.queryByRole('option', { name: /R-REJECTED/ })).not.toBeInTheDocument()
  })

  it('shows a helpful fallback without inventing unknown coordinates', () => {
    render(
      <RouteMap
        destination="Singapore"
        onSelectRoute={vi.fn()}
        origin="Unknown Port"
        recommendedRouteId={null}
        routes={[]}
        selectedRouteId={null}
      />,
    )

    const mapRegion = screen.getByLabelText('Interactive route map')
    expect(within(mapRegion).getByRole('status', { name: /Map coordinates unavailable/ })).toHaveTextContent('Unknown Port')
    expect(screen.queryByRole('img', { name: /Map showing/ })).not.toBeInTheDocument()
  })

  it('explains when OpenStreetMap tiles fail to load', () => {
    render(<RouteMapHarness />)
    fireEvent.click(screen.getByRole('button', { name: 'Simulate tile error' }))

    expect(screen.getByRole('status')).toHaveTextContent('Basemap tiles could not load')
  })
})
