import { describe, expect, it } from 'vitest'
import { CAPTCHA_TIMEOUT_MS, ticketTimeoutMs } from './captcha.store'

describe('ticketTimeoutMs（工单倒计时上限）', () => {
  it('uses the ticket-provided timeoutSeconds when present', () => {
    // zhihuishu QR login tickets carry their own wait limit.
    expect(ticketTimeoutMs({ timeoutSeconds: 180 })).toBe(180_000)
  })

  it('ignores zero / negative / non-numeric timeouts and falls back', () => {
    expect(ticketTimeoutMs({ timeoutSeconds: 0 })).toBe(CAPTCHA_TIMEOUT_MS)
    expect(ticketTimeoutMs({ timeoutSeconds: -5 })).toBe(CAPTCHA_TIMEOUT_MS)
    expect(ticketTimeoutMs({})).toBe(CAPTCHA_TIMEOUT_MS)
  })

  it('default stays at the backend hard timeout (10 minutes)', () => {
    expect(CAPTCHA_TIMEOUT_MS).toBe(10 * 60 * 1000)
  })
})
