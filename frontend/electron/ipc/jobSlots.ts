import type { Platform } from '../types'

/**
 * 每平台一个任务槽位：同平台互斥、跨平台并行。
 *
 * 纯逻辑模块（不 import electron / pythonBridge），vitest 可直接加载；
 * PythonBridge 通过结构子集 SlotBridge 满足约束。
 */
export interface SlotBridge {
  isRunning(): boolean
  pause(): void
  resume(): void
  stop(): void
  resolveTicket(payload: {
    ticketId: string
    accountId: number
    answer?: string
    action?: 'skip'
  }): void
}

/** 一个平台的活跃任务槽位 —— job.handler 编排的最小单位。 */
export interface JobSlot<B extends SlotBridge = SlotBridge> {
  platform: Platform
  jobId: string
  bridge: B
  /** spawn 时授予该任务的内存预算份额（动态剩余分账，见 planner.allocateBudget）。 */
  grantedBudgetGB: number
}

export class JobSlotRegistry<B extends SlotBridge = SlotBridge> {
  private readonly slots = new Map<Platform, JobSlot<B>>()

  isOccupied(platform: Platform): boolean {
    return this.slots.has(platform)
  }

  occupant(platform: Platform): JobSlot<B> | undefined {
    return this.slots.get(platform)
  }

  /** 占用平台槽位；同平台已有活跃任务时抛错（job:start 的互斥闸门）。 */
  acquire(platform: Platform, jobId: string, bridge: B, grantedBudgetGB: number): JobSlot<B> {
    const existing = this.slots.get(platform)
    if (existing) {
      throw new Error(`platform ${platform} already runs job ${existing.jobId}`)
    }
    const slot: JobSlot<B> = { platform, jobId, bridge, grantedBudgetGB }
    this.slots.set(platform, slot)
    return slot
  }

  release(platform: Platform): JobSlot<B> | undefined {
    const slot = this.slots.get(platform)
    if (slot) this.slots.delete(platform)
    return slot
  }

  /**
   * 仅当 bridge 仍是该槽位持有者时释放——旧任务的 Python 进程可能在新任务
   * 启动后仍发出 exit/error 事件，无此守卫会误清新任务的槽位。
   */
  releaseIfCurrent(bridge: B): JobSlot<B> | undefined {
    for (const slot of this.slots.values()) {
      if (slot.bridge === bridge) {
        this.slots.delete(slot.platform)
        return slot
      }
    }
    return undefined
  }

  getByJobId(jobId: string): JobSlot<B> | undefined {
    for (const slot of this.slots.values()) {
      if (slot.jobId === jobId) return slot
    }
    return undefined
  }

  /** 恰有一个活跃槽位时返回它（无 jobId 的旧载荷回落路径）。 */
  soleActiveSlot(): JobSlot<B> | undefined {
    if (this.slots.size !== 1) return undefined
    return this.slots.values().next().value
  }

  activeSlots(): JobSlot<B>[] {
    return [...this.slots.values()]
  }

  /** 其他平台（非 exclude）已授予的预算份额，用于动态剩余分账。 */
  grantedBudgetsExcluding(exclude: Platform): number[] {
    return this.activeSlots()
      .filter((slot) => slot.platform !== exclude)
      .map((slot) => slot.grantedBudgetGB)
  }

  get size(): number {
    return this.slots.size
  }
}

/** 全局唯一实例：主进程内 job.handler / jobState 共享同一槽位表。 */
export const jobSlots = new JobSlotRegistry()
