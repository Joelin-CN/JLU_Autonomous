/**
 * 运行时内存监督（策略 C）——纯决策逻辑。
 *
 * 本模块刻意不 import electron（对齐 planner.ts / jobSlots.ts 先例），
 * vitest 直接加载测试；IO 编排（定时器/测量/通知/IPC）在 ./supervisor。
 */

import type { Platform } from '../types'

/** 距 fail-closed 红线（systemLimitGB）多近时开始介入。 */
export const SUPERVISION_MARGIN_GB = 1.0

/** 两次介入之间的最小间隔（防暂停风暴）。 */
export const DEFAULT_COOLDOWN_MS = 60_000

export interface SupervisionSample {
  systemUsedGB: number
  systemLimitGB: number
  /** 覆盖默认 margin（测试用）。 */
  marginGB?: number
}

export interface SupervisionSlot {
  platform: Platform
  /** 槽位 Python 进程是否存活（暂停态进程仍活着 → true）。 */
  running: boolean
  /** 本监督器已暂停过该槽位（用户手动 resume 时清除，允许再次介入）。 */
  supervisedPaused: boolean
  /** 该平台最新 MEMORY 事件的项目 Chrome 占用（GB）。 */
  projectChromeGB: number
}

export type PauseDecision =
  | { action: 'none' }
  | { action: 'pause'; platform: Platform; systemUsedGB: number; thresholdGB: number }

export function supervisionThresholdGB(sample: SupervisionSample): number {
  return sample.systemLimitGB - (sample.marginGB ?? SUPERVISION_MARGIN_GB)
}

/**
 * 决策：系统占用逼近红线（systemLimitGB − margin）时，对「运行中且未被本
 * 监督器暂停」的槽位里项目占用最大者发出暂停指令。
 *
 * - 只决策暂停、不决策恢复：内存不会因暂停瞬间回落，自动 resume 会与
 *   监督来回打摆；恢复交还用户（UI 手动恢复）。
 * - 冷却期内不再介入（lastEngageAt 距 now 不足 cooldownMs → none）。
 * - 无可暂停对象（全部已暂停/无运行槽位）→ none，红线兜底交给后端
 *   MemoryMonitor 的 fail-closed 急停。
 */
export function decidePauseAction(
  sample: SupervisionSample,
  slots: SupervisionSlot[],
  now: number,
  lastEngageAt: number | null,
  cooldownMs: number = DEFAULT_COOLDOWN_MS,
): PauseDecision {
  const thresholdGB = supervisionThresholdGB(sample)
  if (sample.systemUsedGB < thresholdGB) return { action: 'none' }
  if (lastEngageAt !== null && now - lastEngageAt < cooldownMs) return { action: 'none' }

  let target: SupervisionSlot | null = null
  for (const slot of slots) {
    if (!slot.running || slot.supervisedPaused) continue
    if (target === null || slot.projectChromeGB > target.projectChromeGB) target = slot
  }
  if (target === null) return { action: 'none' }

  return {
    action: 'pause',
    platform: target.platform,
    systemUsedGB: sample.systemUsedGB,
    thresholdGB,
  }
}
