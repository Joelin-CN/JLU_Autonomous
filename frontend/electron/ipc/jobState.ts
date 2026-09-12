import type { Platform } from '../types'
import { jobSlots } from './jobSlots'

/**
 * 任务活跃状态查询（派生自槽位表，不再持有独立布尔）。
 *
 * - 无参：任一平台有活跃任务（设置/AI 配置等全局锁用这个语义）。
 * - 带平台：该平台是否有活跃任务（账号增删改按平台锁）。
 */
export function isJobActive(platform?: Platform): boolean {
  return platform ? jobSlots.isOccupied(platform) : jobSlots.size > 0
}
