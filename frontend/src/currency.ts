export type DisplayCurrency = 'USD' | 'EUR' | 'GBP' | 'INR'

export const USD_DISPLAY_RATES: Readonly<Record<DisplayCurrency, number>> = {
  USD: 1,
  EUR: 0.92,
  GBP: 0.79,
  INR: 83.5,
}

export function convertUsdForDisplay(valueUsd: number, currency: DisplayCurrency): number {
  return valueUsd * USD_DISPLAY_RATES[currency]
}

export function formatCurrency(valueUsd: number, currency: DisplayCurrency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(convertUsdForDisplay(valueUsd, currency))
}

export function formatCurrencyTick(valueUsd: number, currency: DisplayCurrency): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(convertUsdForDisplay(valueUsd, currency))
}
