let active = false

export function isJobActive(): boolean {
  return active
}

export function setJobActive(value: boolean): void {
  active = value
}
