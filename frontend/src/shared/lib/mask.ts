/**
 * Shared PII masking helpers — one format everywhere. Phone logins are the
 * norm for chaoxing accounts (`132****3918`: keep the first 3 and last 4
 * digits); other identifiers (zhihuishu student ids, emails) degrade to a
 * head+tail mask via maskLogin(). Short/odd values degrade gracefully.
 */
export function maskPhone(phone: string): string {
  const value = String(phone ?? '').trim()
  if (!value) return value
  if (value.length <= 4) return value
  if (value.length <= 7) return `${value.slice(0, 3)}****`
  return `${value.slice(0, 3)}****${value.slice(-4)}`
}

/** Mask any login identifier: phone-like → maskPhone, others → head+tail. */
export function maskLogin(name: string): string {
  const value = String(name ?? '').trim()
  if (!value) return value
  if (/^\d{5,}$/.test(value)) return maskPhone(value)
  if (value.length <= 4) return value
  if (value.includes('@')) {
    const [head, domain] = value.split('@')
    return `${head.slice(0, 2)}***@${domain}`
  }
  return `${value.slice(0, 2)}***${value.slice(-2)}`
}
