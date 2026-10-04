import { describe, expect, it } from 'vitest'
import { allocateBudget, computeMemoryPlan } from './planner'

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

describe('allocateBudget（双平台动态剩余分账）', () => {
  it('独跑（无其他平台活跃）拿全额 —— 与现状一致', () => {
    const plan = computeMemoryPlan(31.8, 14.6, 32)
    const allocated = allocateBudget(plan, [])
    expect(allocated.budgetGB).toBeCloseTo(plan.budgetGB)
    expect(allocated.maxConcurrent).toBe(plan.maxConcurrent)
    expect(allocated.systemLimitGB).toBeCloseTo(plan.systemLimitGB)
  })

  it('后启任务拿「全局 − 对方已授予」的剩余份额，并发按份额重算', () => {
    const plan = computeMemoryPlan(31.8, 14.6, 32) // budget ≈ 12.9
    const otherGranted = [5]
    const allocated = allocateBudget(plan, otherGranted)
    expect(allocated.budgetGB).toBeCloseTo(plan.budgetGB - 5)
    expect(allocated.maxConcurrent).toBe(
      Math.max(1, Math.min(Math.floor(allocated.budgetGB / plan.perAccountEstimateGB), plan.cpuCap)),
    )
    // 急停线恒为全机值（两进程共用同一 fail-closed 红线）
    expect(allocated.systemLimitGB).toBeCloseTo(plan.systemLimitGB)
  })

  it('剩余不足 1 账号时给最低保障（受控超卖，由全局测量闸门兜底）', () => {
    const plan = computeMemoryPlan(31.8, 14.6, 32) // budget ≈ 12.9, est 0.7
    const allocated = allocateBudget(plan, [plan.budgetGB - 0.2])
    expect(allocated.budgetGB).toBeCloseTo(plan.perAccountEstimateGB)
    expect(allocated.maxConcurrent).toBe(1)
  })

  it('份额恒不超过全局预算，且授予额不产生负数下溢', () => {
    const plan = computeMemoryPlan(31.8, 14.6, 32)
    // granted=0（对方刚启动还没分到份额）→ 本任务拿全额，即上界
    expect(allocateBudget(plan, [0]).budgetGB).toBeCloseTo(plan.budgetGB)
    // 异常输入（负数/超发）也不会突破 [最低保障, 全局预算] 区间
    const oversubscribed = allocateBudget(plan, [99])
    expect(oversubscribed.budgetGB).toBeGreaterThanOrEqual(plan.perAccountEstimateGB)
    expect(oversubscribed.budgetGB).toBeLessThanOrEqual(plan.budgetGB)
    expect(allocateBudget(plan, [-5]).budgetGB).toBeCloseTo(plan.budgetGB)
  })

  it('份额至少能开 1 个账号（clamp 下界）', () => {
    const plan = computeMemoryPlan(16, 8, 8) // budget = 6
    const allocated = allocateBudget(plan, [5.9])
    expect(allocated.budgetGB).toBeGreaterThanOrEqual(plan.perAccountEstimateGB)
    expect(allocated.maxConcurrent).toBeGreaterThanOrEqual(1)
  })
})
