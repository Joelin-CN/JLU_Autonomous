import { describe, expect, it } from 'vitest'
import {
  DEFAULT_COOLDOWN_MS,
  SUPERVISION_MARGIN_GB,
  decidePauseAction,
  supervisionThresholdGB,
  type SupervisionSlot,
} from './supervision'

function slot(partial: Partial<SupervisionSlot> & { platform: 'chaoxing' | 'zhihuishu' }): SupervisionSlot {
  return { running: true, supervisedPaused: false, projectChromeGB: 0, ...partial }
}

describe('supervisionThresholdGB', () => {
  it('默认 margin 为 1GB', () => {
    expect(supervisionThresholdGB({ systemUsedGB: 0, systemLimitGB: 28.5 })).toBeCloseTo(27.5)
    expect(SUPERVISION_MARGIN_GB).toBe(1.0)
  })

  it('marginGB 可覆盖（测试/调参口）', () => {
    expect(supervisionThresholdGB({ systemUsedGB: 0, systemLimitGB: 28.5, marginGB: 2 })).toBeCloseTo(26.5)
  })
})

describe('decidePauseAction', () => {
  const sample = { systemUsedGB: 27.8, systemLimitGB: 28.5 }

  it('未越预警线时不动作', () => {
    const decision = decidePauseAction(
      { systemUsedGB: 26.0, systemLimitGB: 28.5 },
      [slot({ platform: 'chaoxing', projectChromeGB: 5 })],
      now(),
      null,
    )
    expect(decision).toEqual({ action: 'none' })
  })

  it('越线时暂停占用较大的平台槽位', () => {
    const decision = decidePauseAction(
      sample,
      [
        slot({ platform: 'chaoxing', projectChromeGB: 4.2 }),
        slot({ platform: 'zhihuishu', projectChromeGB: 6.9 }),
      ],
      now(),
      null,
    )
    expect(decision.action).toBe('pause')
    if (decision.action === 'pause') {
      expect(decision.platform).toBe('zhihuishu')
      expect(decision.systemUsedGB).toBeCloseTo(27.8)
      expect(decision.thresholdGB).toBeCloseTo(27.5)
    }
  })

  it('单平台运行同样生效', () => {
    const decision = decidePauseAction(
      sample,
      [slot({ platform: 'chaoxing', projectChromeGB: 0.1 })],
      now(),
      null,
    )
    expect(decision.action).toBe('pause')
    if (decision.action === 'pause') expect(decision.platform).toBe('chaoxing')
  })

  it('冷却期内不重复介入', () => {
    const t = 1_000_000
    const first = decidePauseAction(sample, [slot({ platform: 'chaoxing' })], t, null)
    expect(first.action).toBe('pause')
    const duringCooldown = decidePauseAction(
      sample,
      [slot({ platform: 'chaoxing' })],
      t + DEFAULT_COOLDOWN_MS - 1,
      t,
    )
    expect(duringCooldown).toEqual({ action: 'none' })
  })

  it('冷却期过后可再次介入（另一平台）', () => {
    const t = 1_000_000
    const later = decidePauseAction(
      sample,
      [slot({ platform: 'zhihuishu', projectChromeGB: 3 })],
      t + DEFAULT_COOLDOWN_MS,
      t,
    )
    expect(later.action).toBe('pause')
    if (later.action === 'pause') expect(later.platform).toBe('zhihuishu')
  })

  it('已被监督暂停的槽位跳过，全暂停时不再动作（兜底交 fail-closed）', () => {
    const decision = decidePauseAction(
      sample,
      [
        slot({ platform: 'chaoxing', supervisedPaused: true }),
        slot({ platform: 'zhihuishu', supervisedPaused: true }),
      ],
      now(),
      null,
    )
    expect(decision).toEqual({ action: 'none' })
  })

  it('用户手动 resume 清除标记后允许再次介入', () => {
    const decision = decidePauseAction(
      sample,
      [slot({ platform: 'chaoxing', supervisedPaused: false })],
      now(),
      null,
    )
    expect(decision.action).toBe('pause')
  })

  it('无运行槽位时不动作', () => {
    const decision = decidePauseAction(
      sample,
      [slot({ platform: 'chaoxing', running: false })],
      now(),
      null,
    )
    expect(decision).toEqual({ action: 'none' })
  })

  it('恰好压线（== 阈值）视为越线', () => {
    const decision = decidePauseAction(
      { systemUsedGB: 27.5, systemLimitGB: 28.5 },
      [slot({ platform: 'chaoxing' })],
      now(),
      null,
    )
    expect(decision.action).toBe('pause')
  })
})

function now(): number {
  return Date.now()
}
