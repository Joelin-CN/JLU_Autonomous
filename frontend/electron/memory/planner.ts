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

/**
 * 双平台并行时的动态剩余分账：新任务预算份额 =
 *   clamp(全局预算 − 其他活跃任务已授予之和, 最低保障 1 账号, 全局预算)。
 *
 * 「授予额」允许受控超卖——对方实际占用低于其份额时，本任务仍可启动；两平台
 * Python 进程的内存闸门（gate_open）实测的都是全局 Chrome 占用（profile 同根
 * 目录），实际内存天然收敛不超单机预算。systemLimitGB 恒保持全机值：两进程
 * 共用同一 fail-closed 急停线，任何一方触线都会硬停，红线不破。
 *
 * 前置条件：plan 本身已通过「预算 ≥ 单实例估计」检查（见 job.handler job:start），
 * 因此 clamp 后份额恒 ≥ 1 账号；maxConcurrent 按份额以 computeMemoryPlan 同
 * 一公式重算。
 */
export function allocateBudget(
  plan: MemoryPlan,
  grantedToOthers: number[],
): MemoryPlan {
  const granted = grantedToOthers.reduce((sum, g) => sum + Math.max(0, g), 0)
  const est = Math.max(plan.perAccountEstimateGB, 0.1)
  const shareGB = Math.min(Math.max(plan.budgetGB - granted, est), plan.budgetGB)
  const memMax = Math.max(1, Math.floor(shareGB / est))
  return {
    ...plan,
    budgetGB: shareGB,
    memMax,
    maxConcurrent: Math.max(1, Math.min(memMax, plan.cpuCap)),
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
