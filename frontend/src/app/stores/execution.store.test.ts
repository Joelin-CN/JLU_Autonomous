import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useExecutionStore } from './execution.store'
import type { StartJobPayload } from '@/shared/lib/types'

// 渲染层在浏览器外的桩：localStorage（platform/settings 持久化）与
// window（apiClient 据此选择 Mock 实现）。
const store = new Map<string, string>()
;(globalThis as any).localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
}

function payload(platform: 'chaoxing' | 'zhihuishu', accounts: string[]): StartJobPayload {
  return {
    platform,
    objective: 'catchup',
    strategy: 'balanced',
    mode: 'full-auto',
    courses: [],
    accounts,
  }
}

async function startJob(storeApi: ReturnType<typeof useExecutionStore>, p: StartJobPayload) {
  const promise = storeApi.startJob(p)
  await vi.advanceTimersByTimeAsync(400)
  await promise
}

describe('execution.store 双平台槽位与事件路由', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.useRealTimers()
    store.clear()
  })

  it('双平台并行：事件按 jobId 路由到各自槽位，互不串扰', async () => {
    const execution = useExecutionStore()
    expect(execution.visibleSlots.length).toBe(0)

    await startJob(execution, payload('chaoxing', ['0', '1']))
    await startJob(execution, payload('zhihuishu', ['0']))

    // 双槽各自持 jobId 与平台归属
    expect(execution.slots.chaoxing.jobId).toBeTruthy()
    expect(execution.slots.zhihuishu.jobId).toBeTruthy()
    expect(execution.slots.chaoxing.jobId).not.toBe(execution.slots.zhihuishu.jobId)
    expect(execution.isRunning).toBe(true)
    expect(execution.isRunningOn('chaoxing')).toBe(true)
    expect(execution.isRunningOn('zhihuishu')).toBe(true)

    // 推进时间 → mock 事件流按 jobId 分流，两槽泳道各自推进
    await vi.advanceTimersByTimeAsync(3000)
    expect(execution.slots.chaoxing.lanes.length).toBe(2)
    expect(execution.slots.zhihuishu.lanes.length).toBe(1)
    expect(execution.slots.chaoxing.progress).toBeGreaterThan(0)
    expect(execution.slots.zhihuishu.progress).toBeGreaterThan(0)
    expect(execution.slots.chaoxing.status).toBe('running')
    expect(execution.slots.zhihuishu.status).toBe('running')
  })

  it('停止一个平台任务只终态该槽，另一槽继续运行', async () => {
    const execution = useExecutionStore()
    await startJob(execution, payload('chaoxing', ['0']))
    await startJob(execution, payload('zhihuishu', ['0']))
    await vi.advanceTimersByTimeAsync(1000)

    const stopPromise = execution.stopJob('zhihuishu')
    await vi.advanceTimersByTimeAsync(400)
    await stopPromise

    expect(execution.slots.zhihuishu.status).toBe('stopped')
    expect(execution.slots.chaoxing.status).toBe('running')
    expect(execution.isRunning).toBe(true)
    expect(execution.visibleSlots.length).toBe(2)

    // 关闭已停止的槽不影响运行中的槽
    execution.reset('zhihuishu')
    expect(execution.slots.zhihuishu.status).toBe('idle')
    expect(execution.slots.chaoxing.status).toBe('running')
  })

  it('同平台重复启动覆盖旧任务状态（UI 侧新任务重置该槽）', async () => {
    const execution = useExecutionStore()
    await startJob(execution, payload('chaoxing', ['0']))
    const firstJobId = execution.slots.chaoxing.jobId
    await startJob(execution, payload('chaoxing', ['3']))

    expect(execution.slots.chaoxing.jobId).not.toBe(firstJobId)
    expect(execution.slots.chaoxing.lanes.map((l) => l.accountId)).toEqual(['3'])
    // 智慧树槽不受影响
    expect(execution.slots.zhihuishu.status).toBe('idle')
  })

  it('错误事件的错误信息落在对应平台的槽位', async () => {
    const execution = useExecutionStore()
    await startJob(execution, payload('chaoxing', ['0']))
    await startJob(execution, payload('zhihuishu', ['0']))

    // mock 不主动发错误；直接验证 slotByJobId 的路由判定
    const zhJobId = execution.slots.zhihuishu.jobId!
    expect(execution.slotByJobId(zhJobId)?.platform).toBe('zhihuishu')
    expect(execution.slotByJobId('job_unknown')).toBeNull()
  })
})
