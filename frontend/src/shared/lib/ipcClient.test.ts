import { describe, it, expect } from 'vitest'
import { stripInvokeErrorPrefix } from './ipcClient'

describe('stripInvokeErrorPrefix', () => {
  it('strips the ipcRenderer.invoke wrapper', () => {
    const raw = "Error invoking remote method 'balance:query': Error: volcengine-python-sdk is not installed"
    expect(stripInvokeErrorPrefix(raw)).toBe('volcengine-python-sdk is not installed')
  })

  it('strips the wrapper without a nested Error: prefix', () => {
    const raw = "Error invoking remote method 'settings:set': Error: Python 路径无效：路径不存在"
    expect(stripInvokeErrorPrefix(raw)).toBe('Python 路径无效：路径不存在')
  })

  it('leaves plain messages untouched', () => {
    expect(stripInvokeErrorPrefix('余额查询超时（30 秒未返回）。')).toBe('余额查询超时（30 秒未返回）。')
  })

  it('returns empty for wrapper-only noise', () => {
    expect(stripInvokeErrorPrefix('Error: ')).toBe('')
  })
})
