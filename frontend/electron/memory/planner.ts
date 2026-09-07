import os from 'os'
import { execFile } from 'child_process'

export const BUDGET_RATIO = 0.75
export const PER_ACCOUNT_INITIAL_GB = 0.7
export const EMERGENCY_MARGIN_GB = 1.0

export interface MemoryPlan {
  totalGB: number
  baselineGB: number
  budgetGB: number
  cpuCap: number
  memMax: number
  maxConcurrent: number
  systemLimitGB: number
  perAccountEstimateGB: number
}

export function computeMemoryPlan(
  totalGB: number,
  baselineGB: number,
  threads: number,
  perAccountEstimateGB: number = PER_ACCOUNT_INITIAL_GB,
): MemoryPlan {
  const budgetGB = (totalGB - baselineGB) * BUDGET_RATIO
  const cpuCap = Math.max(2, Math.floor(threads) - 2)
  const memMax = Math.max(1, Math.floor(budgetGB / perAccountEstimateGB))
  const maxConcurrent = Math.max(1, Math.min(memMax, cpuCap))
  return {
    totalGB,
    baselineGB,
    budgetGB,
    cpuCap,
    memMax,
    maxConcurrent,
    systemLimitGB: baselineGB + budgetGB + EMERGENCY_MARGIN_GB,
    perAccountEstimateGB,
  }
}

function runPs(script: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      'powershell',
      ['-NoProfile', '-NonInteractive', '-Command', script],
      { timeout: 20000, windowsHide: true },
      (err, stdout, stderr) => {
        if (err || !stdout.trim()) reject(new Error((stderr || '').trim().slice(0, 200)))
        else resolve(stdout.trim())
      },
    )
  })
}

export async function measureSystemUsedGB(): Promise<number> {
  const out = await runPs(
    '$os=Get-CimInstance Win32_OperatingSystem;$cs=Get-CimInstance Win32_ComputerSystem;' +
      '$u=$cs.TotalPhysicalMemory-($os.FreePhysicalMemory*1024);' +
      '[Console]::Out.Write([string][math]::Round($u/1GB,3))',
  )
  return Number(out)
}

export async function measureProjectChromeGB(profileRoot: string): Promise<number> {
  const esc = profileRoot.replace(/'/g, "''")
  const out = await runPs(
    `$p=Get-CimInstance Win32_Process -Filter "Name='chrome.exe'";` +
      `$m=$p|Where-Object{$_.CommandLine -like '*${esc}*'};` +
      `$s=($m|Measure-Object -Property WorkingSetSize -Sum).Sum;` +
      `[Console]::Out.Write([string]$s)`,
  )
  return Number(out) / 1024 ** 3
}
