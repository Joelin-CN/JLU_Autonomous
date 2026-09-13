import type { Platform, Ticket, TicketKind } from './types'

/**
 * 平台注册表 —— 前端唯一的平台差异事实源（docs/standards/directory.md §3：
 * 平台差异只通过数据模型 platform 字段与能力矩阵表达）。
 *
 * - PLATFORM_META：展示属性（名称/徽标色/图标），供侧栏切换器、头部徽标、
 *   工单平台 tag 等复用。
 * - PLATFORM_CAPABILITIES：能力矩阵，驱动任务按钮组的显隐/置灰、设置页
 *   账号表单字段的裁剪。智慧树 M4（答题求解）落地后只需改这里。
 */

export interface PlatformMeta {
  key: Platform
  /** 完整名（用于首次出现/正式场合）。 */
  label: string
  /** 短名（用于徽标、点阵图例等紧凑场合）。 */
  shortLabel: string
  /** 徽标主题色（侧栏切换器选中态、平台 tag、点阵分块边框）。 */
  color: string
  /** 字符图标。 */
  icon: string
  /** 默认登录页 host：账号表格「登录网址」列显示「默认」标签的判定依据。
   *  无此字段的平台（如智慧树固定登录中心）不展示该列。 */
  defaultLoginHost?: string
}

export interface PlatformTaskCapabilities {
  scanOnly: boolean
  fullAuto: boolean
  /** 覆盖「全自动」按钮文案（智慧树 full = 视频任务）。 */
  fullAutoLabel?: string
  solveOnly: boolean
  /** 置灰理由（tooltip）。 */
  solveOnlyHint?: string
  contentOnly: boolean
  contentOnlyHint?: string
  dryRun: boolean
}

export interface PlatformCapabilities {
  /** 账号表单是否含「登录网址」字段（智慧树走固定登录中心，无此概念）。 */
  accountWebsiteField: boolean
  /** 任务运行期扫码登录（二维码工单，扫码后自动继续）。 */
  qrLogin: boolean
  tasks: PlatformTaskCapabilities
}

export const PLATFORMS: readonly Platform[] = ['chaoxing', 'zhihuishu'] as const

export function isPlatform(value: unknown): value is Platform {
  return value === 'chaoxing' || value === 'zhihuishu'
}

export const PLATFORM_META: Record<Platform, PlatformMeta> = {
  chaoxing: {
    key: 'chaoxing',
    label: '超星学习通',
    shortLabel: '超星',
    color: '#4f7cff',
    icon: '📘',
    defaultLoginHost: 'passport2.chaoxing.com',
  },
  zhihuishu: {
    key: 'zhihuishu',
    label: '智慧树',
    shortLabel: '智慧树',
    color: '#3ec98e',
    icon: '🌳',
  },
}

export const PLATFORM_CAPABILITIES: Record<Platform, PlatformCapabilities> = {
  chaoxing: {
    accountWebsiteField: true,
    qrLogin: false,
    tasks: {
      scanOnly: true,
      fullAuto: true,
      solveOnly: true,
      contentOnly: true,
      dryRun: true,
    },
  },
  zhihuishu: {
    accountWebsiteField: false,
    qrLogin: true,
    tasks: {
      scanOnly: true,
      fullAuto: true,
      fullAutoLabel: '全自动（视频）',
      // M4（答题求解）未落地 —— docs/roadmap/zhihuishu.md。
      solveOnly: false,
      solveOnlyHint: '智慧树答题求解（M4）开发中，当前仅支持视频任务',
      contentOnly: false,
      contentOnlyHint: '智慧树内容任务即视频任务，请使用「全自动（视频）」',
      dryRun: true,
    },
  },
}

/* ── 工单形态 ── */

/** 需要阻塞式弹窗交互（CaptchaModal）的工单形态。 */
export const INTERACTIVE_TICKET_KINDS: readonly TicketKind[] = ['captcha', 'qrcode', 'hint']

export function isInteractiveTicket(ticket: Pick<Ticket, 'kind'>): boolean {
  return ticket.kind != null && (INTERACTIVE_TICKET_KINDS as readonly string[]).includes(ticket.kind)
}
