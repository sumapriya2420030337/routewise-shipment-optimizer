type Coordinate = [number, number]

type CityCoordinate = {
  coordinates: Coordinate
  countryCodes: string[]
}

const cityCoordinates: Record<string, CityCoordinate> = {
  'los angeles': { coordinates: [34.0522, -118.2437], countryCodes: ['US'] },
  'new york': { coordinates: [40.7128, -74.006], countryCodes: ['US'] },
  vancouver: { coordinates: [49.2827, -123.1207], countryCodes: ['CA'] },
  toronto: { coordinates: [43.6532, -79.3832], countryCodes: ['CA'] },
  'mexico city': { coordinates: [19.4326, -99.1332], countryCodes: ['MX'] },
  'sao paulo': { coordinates: [-23.5505, -46.6333], countryCodes: ['BR'] },
  london: { coordinates: [51.5072, -0.1276], countryCodes: ['GB', 'UK'] },
  rotterdam: { coordinates: [51.9244, 4.4777], countryCodes: ['NL'] },
  hamburg: { coordinates: [53.5511, 9.9937], countryCodes: ['DE'] },
  istanbul: { coordinates: [41.0082, 28.9784], countryCodes: ['TR'] },
  dubai: { coordinates: [25.2048, 55.2708], countryCodes: ['AE', 'UAE'] },
  mumbai: { coordinates: [19.076, 72.8777], countryCodes: ['IN'] },
  singapore: { coordinates: [1.3521, 103.8198], countryCodes: ['SG'] },
  shanghai: { coordinates: [31.2304, 121.4737], countryCodes: ['CN'] },
  tokyo: { coordinates: [35.6762, 139.6503], countryCodes: ['JP'] },
  sydney: { coordinates: [-33.8688, 151.2093], countryCodes: ['AU'] },
}

const countryCodesByName: Record<string, string> = {
  'united states': 'US',
  'united states of america': 'US',
  usa: 'US',
  canada: 'CA',
  mexico: 'MX',
  brazil: 'BR',
  'united kingdom': 'GB',
  'great britain': 'GB',
  england: 'GB',
  netherlands: 'NL',
  germany: 'DE',
  turkey: 'TR',
  turkiye: 'TR',
  'united arab emirates': 'AE',
  uae: 'AE',
  india: 'IN',
  china: 'CN',
  japan: 'JP',
  australia: 'AU',
  singapore: 'SG',
}

function normalizeLocationPart(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLocaleLowerCase()
}

export function resolveMapCoordinate(location: string): Coordinate | null {
  const parts = location.split(',')
  const city = cityCoordinates[normalizeLocationPart(parts[0] ?? '')]
  if (!city) return null

  const suppliedCountry = parts.at(-1)?.trim()
  if (suppliedCountry) {
    const normalizedCountry = normalizeLocationPart(suppliedCountry)
    const countryCode = countryCodesByName[normalizedCountry] ?? normalizedCountry.toUpperCase()
    if (!city.countryCodes.includes(countryCode)) return null
  }
  return city.coordinates
}
