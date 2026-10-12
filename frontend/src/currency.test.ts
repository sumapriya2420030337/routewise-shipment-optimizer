import { describe, expect, it } from 'vitest'
import { convertUsdForDisplay, formatCurrency, USD_DISPLAY_RATES } from './currency'

describe('display-only currency conversion', () => {
  it('uses a fixed approximate INR rate and formats the converted value', () => {
    const amountUsd = 15_000
    expect(USD_DISPLAY_RATES.INR).toBe(83.5)
    expect(convertUsdForDisplay(amountUsd, 'INR')).toBe(1_252_500)
    expect(formatCurrency(amountUsd, 'INR')).toBe('₹1,252,500')
  })

  it('leaves the canonical USD amount untouched', () => {
    const amountUsd = 15_000
    convertUsdForDisplay(amountUsd, 'INR')
    expect(amountUsd).toBe(15_000)
    expect(formatCurrency(amountUsd, 'USD')).toBe('$15,000')
  })
})
