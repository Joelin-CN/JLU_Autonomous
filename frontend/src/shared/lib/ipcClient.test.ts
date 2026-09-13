import { describe, it, expect } from 'vitest'
import { classifyTicketKind, stripInvokeErrorPrefix } from './ipcClient'
import type { TicketKind } from './types'

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

describe('classifyTicketKind（工单交互形态判别）', () => {
  const cases: Array<[Record<string, unknown>, boolean, TicketKind | undefined, string]> = [
    // 超星验证码：有图无 timeoutSeconds → 输入型
    [{ imageBase64: 'data:image/png;base64,x' }, true, 'captcha', '有图无超时 → 输入型'],
    // 智慧树扫码登录（auth.py）：图 + timeoutSeconds → 扫码型
    [{ imageBase64: 'data:image/png;base64,x', timeoutSeconds: 180 }, true, 'qrcode', '有图带超时 → 扫码型'],
    // 智慧树滑块：captcha 类型但无图 → 提示型
    [{ message: '请前往浏览器窗口完成滑块拖拽' }, true, 'hint', '无图 captcha → 提示型'],
    // 被动工单不判别
    [{ type: 'warning' }, false, undefined, '非 captcha 类型保持被动'],
    // 非正数 timeoutSeconds 不应把输入型误判为扫码型
    [{ imageBase64: 'data:image/png;base64,x', timeoutSeconds: 0 }, true, 'captcha', 'timeoutSeconds<=0 忽略'],
  ]

  it.each(cases)('%s → %s（%s）', (ticket, isCaptcha, expected) => {
    expect(classifyTicketKind(ticket, isCaptcha)).toBe(expected)
  })
})
