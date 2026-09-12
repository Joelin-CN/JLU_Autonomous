import { describe, expect, it } from 'vitest'
import { migrateLegacySettings } from './settings.store'

describe('migrateLegacySettings（旧品牌持久化结构迁移）', () => {
  it('moves the legacy single accountsFilePath into the chaoxing bucket', () => {
    const migrated = migrateLegacySettings({
      theme: 'dark',
      accountsFilePath: 'D:/custom/chaoxing.txt',
    })
    expect(migrated.theme).toBe('dark')
    expect(migrated.accountsFilePaths).toEqual({
      chaoxing: 'D:/custom/chaoxing.txt',
      zhihuishu: '',
    })
    expect((migrated as Record<string, unknown>).accountsFilePath).toBeUndefined()
  })

  it('keeps the new shape untouched when only new-style data exists', () => {
    const migrated = migrateLegacySettings({
      accountsFilePaths: { chaoxing: 'a.txt', zhihuishu: 'b.txt' },
    })
    expect(migrated.accountsFilePaths).toEqual({ chaoxing: 'a.txt', zhihuishu: 'b.txt' })
  })

  it('defaults both buckets when no path was ever set', () => {
    const migrated = migrateLegacySettings({ dryRun: true })
    expect(migrated.accountsFilePaths).toEqual({ chaoxing: '', zhihuishu: '' })
    expect(migrated.dryRun).toBe(true)
  })
})
