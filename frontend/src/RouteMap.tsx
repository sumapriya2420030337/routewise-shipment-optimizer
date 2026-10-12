import { useEffect, useState } from 'react'
import {
  CircleMarker,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import type { RouteCandidate } from './types'
import { resolveMapCoordinate } from './routeCoordinates'
import 'leaflet/dist/leaflet.css'

type Coordinate = [number, number]

function routeColor(mode: string): string {
  switch (mode) {
    case 'air': return '#7656d6'
    case 'ocean': return '#168c9a'
    case 'rail': return '#c47a16'
    case 'road': return '#3568d4'
    default: return '#606b7c'
  }
}

function FitToEndpoints({
  origin,
  destination,
}: {
  origin: Coordinate
  destination: Coordinate
}) {
  const map = useMap()

  useEffect(() => {
    map.fitBounds([origin, destination], { padding: [36, 36], maxZoom: 6 })
    map.invalidateSize()
  }, [destination, map, origin])

  return null
}

function MapTiles() {
  const [tilesLoaded, setTilesLoaded] = useState(false)
  const [tilesFailed, setTilesFailed] = useState(false)

  return (
    <>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'
        eventHandlers={{
          load: () => setTilesLoaded(true),
          tileerror: () => {
            setTilesFailed(true)
            setTilesLoaded(true)
          },
        }}
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {!tilesLoaded && <div className="route-map-state" role="status">Loading OpenStreetMap tiles…</div>}
      {tilesFailed && (
        <div className="route-map-state error" role="status">
          Basemap tiles could not load. Endpoint markers and the schematic connection remain visible.
        </div>
      )}
    </>
  )
}

export function RouteMap({
  origin,
  destination,
  routes,
  recommendedRouteId,
  selectedRouteId,
  onSelectRoute,
}: {
  origin: string
  destination: string
  routes: RouteCandidate[]
  recommendedRouteId: string | null
  selectedRouteId: string | null
  onSelectRoute: (routeId: string) => void
}) {
  const originCoordinate = resolveMapCoordinate(origin)
  const destinationCoordinate = resolveMapCoordinate(destination)
  const eligibleRoutes = routes.filter((route) => route.is_feasible)
  const selectedRoute =
    eligibleRoutes.find((route) => route.route_id === selectedRouteId) ??
    eligibleRoutes.find((route) => route.route_id === recommendedRouteId) ??
    null
  const endpointsKnown = originCoordinate !== null && destinationCoordinate !== null
  const lineColor = selectedRoute ? routeColor(selectedRoute.route_mode) : '#7b8494'

  return (
    <section className="route-map-panel" aria-label="Interactive route map">
      <div className="route-map-heading">
        <div>
          <p className="eyebrow">ROUTE MAP</p>
          <h3>Journey overview</h3>
        </div>
        {eligibleRoutes.length > 0 && (
          <label className="route-map-picker">
            <span>Display eligible candidate</span>
            <select
              aria-label="Display eligible candidate on map"
              className="form-control"
              onChange={(event) => onSelectRoute(event.target.value)}
              value={selectedRoute?.route_id ?? ''}
            >
              {eligibleRoutes.map((route) => (
                <option key={route.route_id} value={route.route_id}>
                  {route.route_id} · {route.route_mode}
                  {route.route_id === recommendedRouteId ? ' · recommended' : ''}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {selectedRoute ? (
        <div className="route-map-summary" aria-live="polite">
          <strong>{selectedRoute.route_id} · {selectedRoute.route_mode} · eligible</strong>
          <span>
            USD {selectedRoute.cost_usd.toLocaleString()} · {selectedRoute.transit_time_days.toFixed(1)} days
            {' · '}delay {Math.round(selectedRoute.delay_probability * 1000) / 10}%
          </span>
        </div>
      ) : (
        <p className="route-map-no-route" role="status">
          No eligible candidate is available to display. Endpoints are shown without a route connection.
        </p>
      )}

      {!endpointsKnown ? (
        <div aria-label="Map coordinates unavailable" className="route-map-fallback" role="status">
          <strong>Map coordinates unavailable</strong>
          <p>
            {originCoordinate ? '' : `Origin “${origin}”`}
            {!originCoordinate && !destinationCoordinate ? ' and ' : ''}
            {destinationCoordinate ? '' : `destination “${destination}”`}
            {' '}is not in RouteWise’s offline city catalog. No location or route geometry has been guessed.
          </p>
        </div>
      ) : (
        <div className="route-map-frame">
          <MapContainer
            aria-label={`Map showing ${origin} and ${destination}`}
            className="route-map-canvas"
            scrollWheelZoom
            zoom={3}
            center={originCoordinate}
          >
            <MapTiles key={`${origin}|${destination}`} />
            <FitToEndpoints origin={originCoordinate} destination={destinationCoordinate} />
            <CircleMarker
              center={originCoordinate}
              pathOptions={{ color: '#19734b', fillColor: '#42b883', fillOpacity: 1, weight: 2 }}
              radius={8}
            >
              <Tooltip direction="top" permanent>{`Origin · ${origin}`}</Tooltip>
            </CircleMarker>
            <CircleMarker
              center={destinationCoordinate}
              pathOptions={{ color: '#a63137', fillColor: '#e65b60', fillOpacity: 1, weight: 2 }}
              radius={8}
            >
              <Tooltip direction="top" permanent>{`Destination · ${destination}`}</Tooltip>
            </CircleMarker>
            {selectedRoute && (
              <Polyline
                pathOptions={{ color: lineColor, dashArray: '7 8', opacity: 0.85, weight: 3 }}
                positions={[originCoordinate, destinationCoordinate]}
              />
            )}
          </MapContainer>
        </div>
      )}

      <div className="route-map-legend" aria-label="Map legend">
        <span><i className="route-map-marker origin" />Origin</span>
        <span><i className="route-map-marker destination" />Destination</span>
        {selectedRoute && (
          <span>
            <i className="route-map-line" style={{ borderColor: lineColor }} />
            Selected {selectedRoute.route_mode} candidate
          </span>
        )}
      </div>
      <p className="route-map-disclaimer">
        Candidate costs and transit times are illustrative synthetic estimates, not live carrier information.
        The dashed line is a schematic endpoint connection only—not an actual road, rail, sea, or flight path.
        No route geometry or transfer hubs are available in the current route data.
      </p>
    </section>
  )
}
