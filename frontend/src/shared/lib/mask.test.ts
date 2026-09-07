import { describe, it, expect } from 'vitest'
import { maskPhone, maskLogin } from './mask'

describe('maskPhone', () => {
  it('masks an 11-digit CN mobile number as 3+4', () => {
    expect(maskPhone('13200003918')).toBe('132****3918')
  })

  it('keeps short values as-is', () => {
    expect(maskPhone('')).toBe('')
    expect(maskPhone('1234')).toBe('1234')
  })

  it('masks mid-length values without a tail', () => {
    expect(maskPhone('1234567')).toBe('123****')
  })

  it('handles non-numeric logins via maskLogin', () => {
    expect(maskLogin('student01')).toBe('st***01')
    expect(maskLogin('ab@cqu.edu.cn')).toBe('ab***@cqu.edu.cn')
  })

  it('maskLogin routes digit logins through maskPhone', () => {
    expect(maskLogin('13200003918')).toBe('132****3918')
  })
})
