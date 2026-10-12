"""Offline, deterministic geography checks for supported RouteWise city pairs."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    country_codes: frozenset[str]
    land_network: str
    has_seaport: bool


_LOCATION_ROWS: dict[str, Location] = {
    "los angeles": Location(34.0522, -118.2437, frozenset({"US"}), "north_america", True),
    "new york": Location(40.7128, -74.0060, frozenset({"US"}), "north_america", True),
    "vancouver": Location(49.2827, -123.1207, frozenset({"CA"}), "north_america", True),
    "toronto": Location(43.6532, -79.3832, frozenset({"CA"}), "north_america", True),
    "mexico city": Location(19.4326, -99.1332, frozenset({"MX"}), "north_america", False),
    "sao paulo": Location(-23.5505, -46.6333, frozenset({"BR"}), "south_america", False),
    "london": Location(51.5072, -0.1276, frozenset({"GB", "UK"}), "british_isles", True),
    "rotterdam": Location(51.9244, 4.4777, frozenset({"NL"}), "europe_asia", True),
    "hamburg": Location(53.5511, 9.9937, frozenset({"DE"}), "europe_asia", True),
    "istanbul": Location(41.0082, 28.9784, frozenset({"TR"}), "europe_asia", True),
    "dubai": Location(25.2048, 55.2708, frozenset({"AE", "UAE"}), "europe_asia", True),
    "mumbai": Location(19.0760, 72.8777, frozenset({"IN"}), "europe_asia", True),
    "singapore": Location(1.3521, 103.8198, frozenset({"SG"}), "europe_asia", True),
    "shanghai": Location(31.2304, 121.4737, frozenset({"CN"}), "europe_asia", True),
    "tokyo": Location(35.6762, 139.6503, frozenset({"JP"}), "japan", True),
    "sydney": Location(-33.8688, 151.2093, frozenset({"AU"}), "australia", True),
}

_COUNTRY_ALIASES = {
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "canada": "CA",
    "mexico": "MX",
    "brazil": "BR",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "netherlands": "NL",
    "germany": "DE",
    "turkey": "TR",
    "türkiye": "TR",
    "united arab emirates": "AE",
    "uae": "AE",
    "india": "IN",
    "china": "CN",
    "japan": "JP",
    "australia": "AU",
    "singapore": "SG",
}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_value.casefold().strip())


def resolve_location(value: str) -> Location | None:
    """Resolve a city in the bundled offline coordinate and connectivity catalog."""
    parts = [part.strip() for part in value.split(",")]
    location = _LOCATION_ROWS.get(_normalize(parts[0]))
    if location is None:
        return None
    if len(parts) > 1 and parts[1]:
        country = _normalize(parts[-1])
        country_code = _COUNTRY_ALIASES.get(country, country.upper())
        if country_code not in location.country_codes:
            return None
    return location


def transport_mode_rejection_reason(
    origin: str, destination: str, route_mode: str
) -> str | None:
    """Return a precise reason when a direct single-mode route is not supportable."""
    start = resolve_location(origin)
    end = resolve_location(destination)
    if start is None or end is None:
        missing = []
        if start is None:
            missing.append(f"origin {origin!r}")
        if end is None:
            missing.append(f"destination {destination!r}")
        return (
            "geographic infeasibility cannot be verified for unrecognized "
            + " and ".join(missing)
            + " in the offline city catalog"
        )
    if route_mode == "air":
        return None
    if route_mode == "ocean":
        if start.has_seaport and end.has_seaport:
            return None
        return (
            "geographic infeasibility: direct ocean freight requires supported "
            "seaports at both endpoints"
        )
    if route_mode in {"road", "rail"}:
        if start.land_network == end.land_network:
            return None
        return (
            f"geographic infeasibility: direct {route_mode} freight crosses disconnected land networks "
            "or an ocean; no explicit transfer segments are provided"
        )
    return f"geographic infeasibility: route mode {route_mode!r} is unsupported for a direct route"
