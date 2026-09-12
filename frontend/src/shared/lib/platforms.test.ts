import { describe, expect, it } from 'vitest'
import {
  INTERACTIVE_TICKET_KINDS,
  PLATFORMS,
  PLATFORM_CAPABILITIES,
  PLATFORM_META,
  isInteractiveTicket,
  isPlatform,
} from './platforms'

describe('platforms registry', () => {
  it('covers exactly the two supported platforms', () => {
    expect(PLATFORMS).toEqual(['chaoxing', 'zhihuishu'])
    expect(isPlatform('chaoxing')).toBe(true)
    expect(isPlatform('zhihuishu')).toBe(true)
    expect(isPlatform('ouuc')).toBe(false)
    expect(isPlatform(null)).toBe(false)
  })

  it('gives every platform a complete meta entry', () => {
    for (const p of PLATFORMS) {
      const meta = PLATFORM_META[p]
      expect(meta.key).toBe(p)
      expect(meta.label.length).toBeGreaterThan(0)
      expect(meta.shortLabel.length).toBeGreaterThan(0)
      expect(meta.color).toMatch(/^#[0-9a-f]{6}$/i)
      expect(meta.icon.length).toBeGreaterThan(0)
    }
    // The website-column default label is chaoxing-specific (school login
    // pages); zhihuishu uses a fixed login center and must NOT declare one.
    expect(PLATFORM_META.chaoxing.defaultLoginHost).toContain('chaoxing.com')
    expect(PLATFORM_META.zhihuishu.defaultLoginHost).toBeUndefined()
  })

  it('capability matrix: chaoxing supports the full task set', () => {
    const caps = PLATFORM_CAPABILITIES.chaoxing.tasks
    expect(caps.scanOnly).toBe(true)
    expect(caps.fullAuto).toBe(true)
    expect(caps.solveOnly).toBe(true)
    expect(caps.contentOnly).toBe(true)
    expect(caps.dryRun).toBe(true)
    expect(PLATFORM_CAPABILITIES.chaoxing.accountWebsiteField).toBe(true)
    expect(PLATFORM_CAPABILITIES.chaoxing.qrLogin).toBe(false)
  })

  it('capability matrix: zhihuishu gates quiz solving (M4) behind a hint', () => {
    const caps = PLATFORM_CAPABILITIES.zhihuishu.tasks
    expect(caps.scanOnly).toBe(true)
    expect(caps.fullAuto).toBe(true)
    expect(caps.fullAutoLabel).toContain('视频')
    // M4 (quiz solving) is not implemented — the button must be disabled AND
    // explain why.
    expect(caps.solveOnly).toBe(false)
    expect(caps.solveOnlyHint).toContain('M4')
    expect(caps.contentOnly).toBe(false)
    expect(caps.contentOnlyHint!.length).toBeGreaterThan(0)
    expect(caps.dryRun).toBe(true)
    expect(PLATFORM_CAPABILITIES.zhihuishu.accountWebsiteField).toBe(false)
    expect(PLATFORM_CAPABILITIES.zhihuishu.qrLogin).toBe(true)
  })
})

describe('isInteractiveTicket', () => {
  it('accepts exactly the interactive kinds and rejects the rest', () => {
    for (const kind of INTERACTIVE_TICKET_KINDS) {
      expect(isInteractiveTicket({ kind })).toBe(true)
    }
    expect(isInteractiveTicket({})).toBe(false)
    expect(isInteractiveTicket({ kind: undefined })).toBe(false)
  })
})
