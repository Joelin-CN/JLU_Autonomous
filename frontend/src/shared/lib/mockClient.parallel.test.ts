import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MockApiClient } from './mockClient'
import type { StartJobPayload } from './types'

// MockApiClient touches localStorage in get/setSettings; provide a minimal
// in-memory stub so the store-less paths stay testable in Node.
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

/** 假时钟下 mock 方法内部的 sleep() 需要并发推进才能 resolve：
 *  边推进 ms 毫秒边等待 promise（mock 内部 sleep 最长 300ms）。
 *  预挂一个占位 catch，避免推进期间已 reject 的 promise 被记为 unhandled。 */
async function flush<T>(p: Promise<T>, ms = 500): Promise<T> {
  void p.catch(() => {})
  await vi.advanceTimersByTimeAsync(ms)
  return p
}

async function start(client: MockApiClient, p: StartJobPayload) {
  return flush(client.startJob(p), 400)
}

describe('MockApiClient 双平台并行任务模拟', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    store.clear()
  })

  it('跨平台任务并存：两路事件按 jobId+platform 分流，互不干扰', async () => {
    const client = new MockApiClient()
    const seen: Array<{ jobId: string; platform?: string }> = []
    client.onProgress((e) => seen.push({ jobId: e.jobId, platform: e.platform }))

    const cx = await start(client, payload('chaoxing', ['0', '1']))
    const zh = await start(client, payload('zhihuishu', ['0']))

    expect(cx.platform).toBe('chaoxing')
    expect(zh.platform).toBe('zhihuishu')

    // 两个仿真同时活着，各自的 handle 都可查询
    const cxStatus = await flush(client.getJobStatus(cx.jobId))
    const zhStatus = await flush(client.getJobStatus(zh.jobId))
    expect(cxStatus.status).toBe('running')
    expect(zhStatus.status).toBe('running')

    // 推进时间 → 两路 progress 事件都到达，且 platform 盖章正确
    await vi.advanceTimersByTimeAsync(3000)
    const cxEvents = seen.filter((e) => e.jobId === cx.jobId)
    const zhEvents = seen.filter((e) => e.jobId === zh.jobId)
    expect(cxEvents.length).toBeGreaterThan(0)
    expect(zhEvents.length).toBeGreaterThan(0)
    expect(cxEvents.every((e) => e.platform === 'chaoxing')).toBe(true)
    expect(zhEvents.every((e) => e.platform === 'zhihuishu')).toBe(true)
  })

  it('同平台再启动 = 替换旧仿真（互斥），另一平台不受影响', async () => {
    const client = new MockApiClient()
    const cx1 = await start(client, payload('chaoxing', ['0']))
    const zh = await start(client, payload('zhihuishu', ['0']))
    const cx2 = await start(client, payload('chaoxing', ['2']))

    // 旧超星仿真已被替换：查询抛错；新超星与智慧树均存活
    await expect(flush(client.getJobStatus(cx1.jobId))).rejects.toThrow(/not found/)
    expect((await flush(client.getJobStatus(cx2.jobId))).status).toBe('running')
    expect((await flush(client.getJobStatus(zh.jobId))).status).toBe('running')
  })

  it('停止一个平台任务不影响另一平台继续跑', async () => {
    const client = new MockApiClient()
    const completions: Array<{ jobId: string; success: boolean; platform?: string }> = []
    client.onCompleted((e) => completions.push({ jobId: e.jobId, success: e.success, platform: e.platform }))

    const cx = await start(client, payload('chaoxing', ['0']))
    const zh = await start(client, payload('zhihuishu', ['0']))
    await vi.advanceTimersByTimeAsync(1000)

    await flush(client.stopJob(zh.jobId), 300)

    const zhStop = completions.find((e) => e.jobId === zh.jobId)
    expect(zhStop).toBeDefined()
    expect(zhStop?.success).toBe(false)
    expect(zhStop?.platform).toBe('zhihuishu')

    // 超星任务仍在运行
    expect((await flush(client.getJobStatus(cx.jobId))).status).toBe('running')
    await vi.advanceTimersByTimeAsync(2000)
    expect((await flush(client.getJobStatus(cx.jobId))).status).not.toBe('idle')
  })

  it('演示工单带 jobId（供 resolveCaptcha 双平台路由）', async () => {
    const client = new MockApiClient()
    const tickets: Array<{ id: string; platform?: string; jobId?: string }> = []
    client.onTicket((t) => tickets.push({ id: t.id, platform: t.platform, jobId: t.jobId }))

    const cx = await start(client, payload('chaoxing', ['0']))
    await vi.advanceTimersByTimeAsync(4100)

    const demo = tickets.find((t) => t.platform === 'chaoxing')
    expect(demo).toBeDefined()
    expect(demo?.jobId).toBe(cx.jobId)
  })
})
