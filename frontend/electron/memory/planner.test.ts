import { describe, expect, it } from 'vitest'
import { computeMemoryPlan } from './planner'

describe('computeMemoryPlan', () => {
  it('matches the spec example', () => {
    const p = computeMemoryPlan(31.8, 14.6, 32)
    expect(p.budgetGB).toBeCloseTo((31.8 - 14.6) * 0.75)
    expect(p.cpuCap).toBe(30)
    expect(p.memMax).toBe(Math.floor(p.budgetGB / 0.7))
    expect(p.maxConcurrent).toBe(Math.min(p.memMax, p.cpuCap))
    expect(p.systemLimitGB).toBeCloseTo(14.6 + p.budgetGB + 1.0)
  })

  it('clamps to cpu on small machines', () => {
    const p = computeMemoryPlan(8, 7.5, 4)
    expect(p.cpuCap).toBe(2)
    expect(p.maxConcurrent).toBeLessThanOrEqual(2)
  })
})
