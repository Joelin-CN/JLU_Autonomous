import { afterEach, describe, expect, it } from 'vitest'
import { resetApiClient } from './apiClient'
import { MockApiClient } from './mockClient'

// MockApiClient touches localStorage in get/setSettings; provide a minimal
// in-memory stub so the store-less paths stay testable in Node.
const store = new Map<string, string>()
;(globalThis as any).localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
}

afterEach(() => {
  resetApiClient()
  store.clear()
})

describe('MockApiClient 平台路由', () => {
  it('returns per-platform account buckets (phone logins vs student ids)', async () => {
    const client = new MockApiClient()
    const chaoxing = await client.getAccounts('chaoxing')
    const zhihuishu = await client.getAccounts('zhihuishu')

    expect(chaoxing.length).toBeGreaterThan(0)
    expect(zhihuishu.length).toBeGreaterThan(0)
    for (const account of chaoxing) {
      expect(account.platform).toBe('chaoxing')
      expect(account.username).toMatch(/^1\d{10}$/)
    }
    for (const account of zhihuishu) {
      expect(account.platform).toBe('zhihuishu')
      expect(account.username).toMatch(/^2024\d{6}$/)
    }
  })

  it('scopes courses per platform (mock URLs mirror the real hosts)', async () => {
    const client = new MockApiClient()
    const chaoxingAccounts = await client.getAccounts('chaoxing')
    const zhihuishuAccounts = await client.getAccounts('zhihuishu')

    const chaoxingCourses = await client.getCourses(chaoxingAccounts[0].id, 'chaoxing')
    const zhihuishuCourses = await client.getCourses(zhihuishuAccounts[0].id, 'zhihuishu')

    expect(chaoxingCourses.length).toBeGreaterThan(0)
    expect(zhihuishuCourses.length).toBeGreaterThan(0)
    for (const course of chaoxingCourses) {
      expect(course.url).toContain('mooc1.chaoxing.com')
      expect(course.platform).toBe('chaoxing')
    }
    for (const course of zhihuishuCourses) {
      expect(course.url).toContain('onlineweb.zhihuishu.com')
      expect(course.platform).toBe('zhihuishu')
    }
  })

  it('resolves per-platform default credential file paths', async () => {
    const client = new MockApiClient()
    expect(await client.getAccountsDefaultPath('chaoxing')).toBe('data/passwords/chaoxing.txt')
    expect(await client.getAccountsDefaultPath('zhihuishu')).toBe('data/passwords/zhihuishu.txt')
  })

  it('seeds platform-tagged tickets including zhihuishu interactive forms', () => {
    const client = new MockApiClient()
    // Constructor seeds both platforms' tickets; interactive kinds must carry
    // their platform so attention-queue filtering can group them.
    const seeded = (client as any).tickets as Array<{ platform?: string; kind?: string }>
    expect(seeded.some((t) => t.platform === 'chaoxing')).toBe(true)
    expect(seeded.some((t) => t.platform === 'zhihuishu')).toBe(true)
    expect(seeded.some((t) => t.kind === 'qrcode')).toBe(true)
    expect(seeded.some((t) => t.kind === 'hint')).toBe(true)
  })
})
