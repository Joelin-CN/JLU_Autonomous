/**
 * 运行时内存监督服务（策略 C）——IO 编排层。
 *
 * 主进程周期性用 planner.measureSystemUsedGB 自测系统内存，叠加双路 MEMORY
 * 事件喂入的各平台项目占用，调用 ./supervision 的纯函数决策：接近红线
 * （systemLimitGB − margin）时对占用较大的平台槽位执行整任务暂停 + 系统
 * 通知 + 向渲染层推送监督状态。不自动 resume——恢复交还用户（防抖动）。
 */

import { BrowserWindow, Notification } from 'electron'
import { jobSlots } from '../ipc/jobSlots'
import { getCurrentSettings } from '../ipc/status.handler'
import { measureSystemUsedGB } from './planner'
import { decidePauseAction, type SupervisionSlot } from './supervision'
import type { MemorySupervisionEvent, Platform } from '../types'
import { IPC_CHANNELS } from '../types'

const TICK_MS = 10_000

export interface MemorySupervisorHooks {
  /** 主窗口提供者（发送监督状态到渲染层）。 */
  getMainWindow: () => BrowserWindow | null
  /** 介入回调：由 job.handler 提供真正执行整任务暂停（bridge.pause + 状态更新）。 */
  pauseSlot: (platform: Platform) => void
}

class MemorySupervisor {
  private timer: NodeJS.Timeout | null = null
  private ticking = false
  private getMainWindow: (() => BrowserWindow | null) | null = null
  private pauseSlot: ((platform: Platform) => void) | null = null
  private lastUsage = new Map<Platform, number>()
  private systemLimitGB: number | null = null
  private supervisedPaused = new Set<Platform>()
  private lastEngageAt: number | null = null

  bindHooks(hooks: MemorySupervisorHooks): void {
    this.getMainWindow = hooks.getMainWindow
    this.pauseSlot = hooks.pauseSlot
  }

  /** job:start 拿到槽位后调用；重复调用幂等。 */
  start(systemLimitGB: number): void {
    this.systemLimitGB = systemLimitGB
    if (this.timer) return
    this.timer = setInterval(() => {
      void this.tick()
    }, TICK_MS)
  }

  /** 停表并复位介入痕迹（下次 start 从零开始；before-quit / 全空闲时调用）。 */
  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
    this.ticking = false
    this.lastUsage.clear()
    this.supervisedPaused.clear()
    this.lastEngageAt = null
    this.systemLimitGB = null
  }

  /** MEMORY 事件转发处喂入：各平台最新项目 Chrome 占用（GB）。 */
  noteUsage(platform: Platform, projectChromeGB: number): void {
    if (Number.isFinite(projectChromeGB) && projectChromeGB >= 0) {
      this.lastUsage.set(platform, projectChromeGB)
    }
  }

  /** 用户手动 resume 后清除标记：该平台再次越线时允许监督重新介入。 */
  markResumed(platform: Platform): void {
    this.supervisedPaused.delete(platform)
  }

  private async tick(): Promise<void> {
    if (this.ticking) return
    // 无活跃槽位自动停表（监督只在有任务可保护时运行）。
    if (jobSlots.size === 0) {
      this.stop()
      return
    }
    if (this.systemLimitGB === null) return

    this.ticking = true
    try {
      let systemUsedGB: number
      try {
        systemUsedGB = await measureSystemUsedGB()
      } catch {
        // 测量失败只跳过本轮（对齐后端 MemoryMonitor 的降级语义），监督不死。
        return
      }

      const slots: SupervisionSlot[] = jobSlots.activeSlots().map((slot) => ({
        platform: slot.platform,
        running: slot.bridge.isRunning(),
        supervisedPaused: this.supervisedPaused.has(slot.platform),
        projectChromeGB: this.lastUsage.get(slot.platform) ?? 0,
      }))

      const decision = decidePauseAction(
        { systemUsedGB, systemLimitGB: this.systemLimitGB },
        slots,
        Date.now(),
        this.lastEngageAt,
      )
      if (decision.action !== 'pause') return

      this.supervisedPaused.add(decision.platform)
      this.lastEngageAt = Date.now()
      this.pauseSlot?.(decision.platform)

      const event: MemorySupervisionEvent = {
        type: 'MEMORY_SUPERVISION',
        state: 'engaged',
        systemUsedGB: round(systemUsedGB),
        thresholdGB: round(decision.thresholdGB),
        systemLimitGB: round(this.systemLimitGB),
        platform: decision.platform,
        at: new Date().toISOString(),
        message:
          `系统内存 ${systemUsedGB.toFixed(1)}GB 逼近红线 ${decision.thresholdGB.toFixed(1)}GB，` +
          `已自动暂停 ${decision.platform} 任务（恢复请手动点击「继续」）。`,
      }
      this.emit(event)
      if (getCurrentSettings().notifications) {
        new Notification({ title: 'JLU 学习助手 · 内存监督', body: event.message }).show()
      }
    } finally {
      this.ticking = false
    }
  }

  private emit(event: MemorySupervisionEvent): void {
    const win = this.getMainWindow?.() ?? null
    if (win && !win.isDestroyed()) {
      win.webContents.send(IPC_CHANNELS.ON_MEMORY_SUPERVISION, event)
    }
  }
}

function round(value: number): number {
  return Math.round(value * 100) / 100
}

export const memorySupervisor = new MemorySupervisor()
