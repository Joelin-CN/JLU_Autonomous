import { describe, expect, it } from 'vitest'
import { JobSlotRegistry, type SlotBridge } from './jobSlots'

function fakeBridge(): SlotBridge {
  return {
    isRunning: () => true,
    pause: () => {},
    resume: () => {},
    stop: () => {},
    resolveTicket: () => {},
  }
}

describe('JobSlotRegistry（同平台互斥 / 跨平台并行）', () => {
  it('同平台 acquire 二次占用抛错，跨平台可并行', () => {
    const reg = new JobSlotRegistry()
    reg.acquire('chaoxing', 'job_1', fakeBridge(), 10)
    expect(() => reg.acquire('chaoxing', 'job_2', fakeBridge(), 5)).toThrow(/already runs job job_1/)

    reg.acquire('zhihuishu', 'job_3', fakeBridge(), 4)
    expect(reg.size).toBe(2)
    expect(reg.isOccupied('chaoxing')).toBe(true)
    expect(reg.isOccupied('zhihuishu')).toBe(true)
  })

  it('getByJobId 在双任务下按 jobId 精确路由', () => {
    const reg = new JobSlotRegistry()
    reg.acquire('chaoxing', 'job_cx', fakeBridge(), 10)
    reg.acquire('zhihuishu', 'job_zh', fakeBridge(), 4)

    expect(reg.getByJobId('job_cx')?.platform).toBe('chaoxing')
    expect(reg.getByJobId('job_zh')?.platform).toBe('zhihuishu')
    expect(reg.getByJobId('job_missing')).toBeUndefined()
  })

  it('releaseIfCurrent 仅释放持有该 bridge 的槽位（防陈旧事件误清）', () => {
    const reg = new JobSlotRegistry()
    const bridgeA = fakeBridge()
    const bridgeB = fakeBridge()
    reg.acquire('chaoxing', 'job_1', bridgeA, 10)
    reg.acquire('zhihuishu', 'job_2', bridgeB, 4)

    // 旧任务的 bridge（不在任何槽位）不产生副作用
    expect(reg.releaseIfCurrent(fakeBridge())).toBeUndefined()
    expect(reg.size).toBe(2)

    // 释放 chaoxing 槽不影响 zhihuishu
    const released = reg.releaseIfCurrent(bridgeA)
    expect(released?.platform).toBe('chaoxing')
    expect(reg.size).toBe(1)
    expect(reg.isOccupied('zhihuishu')).toBe(true)

    // 同一 bridge 的迟到事件再次到达 → 无操作
    expect(reg.releaseIfCurrent(bridgeA)).toBeUndefined()
    expect(reg.size).toBe(1)
  })

  it('soleActiveSlot：恰一个活跃槽时返回，零或二个时 undefined（旧载荷回落语义）', () => {
    const reg = new JobSlotRegistry()
    expect(reg.soleActiveSlot()).toBeUndefined()

    reg.acquire('chaoxing', 'job_1', fakeBridge(), 10)
    expect(reg.soleActiveSlot()?.jobId).toBe('job_1')

    reg.acquire('zhihuishu', 'job_2', fakeBridge(), 4)
    expect(reg.soleActiveSlot()).toBeUndefined()
  })

  it('grantedBudgetsExcluding 返回其他平台的已授予预算（动态分账输入）', () => {
    const reg = new JobSlotRegistry()
    expect(reg.grantedBudgetsExcluding('chaoxing')).toEqual([])

    reg.acquire('chaoxing', 'job_1', fakeBridge(), 10.5)
    expect(reg.grantedBudgetsExcluding('zhihuishu')).toEqual([10.5])
    expect(reg.grantedBudgetsExcluding('chaoxing')).toEqual([])

    reg.acquire('zhihuishu', 'job_2', fakeBridge(), 3)
    expect(reg.grantedBudgetsExcluding('chaoxing')).toEqual([3])
  })

  it('release(platform) 释放指定槽并可重新占用', () => {
    const reg = new JobSlotRegistry()
    reg.acquire('chaoxing', 'job_1', fakeBridge(), 10)
    expect(reg.release('chaoxing')?.jobId).toBe('job_1')
    expect(reg.release('chaoxing')).toBeUndefined()

    reg.acquire('chaoxing', 'job_2', fakeBridge(), 8)
    expect(reg.getByJobId('job_2')?.platform).toBe('chaoxing')
  })
})
