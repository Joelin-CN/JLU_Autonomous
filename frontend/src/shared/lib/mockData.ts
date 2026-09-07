// ── Mock Data Generator ──
// Generates realistic Chinese university (超星学习通) data for frontend development

import type {
  Account,
  Course,
  SectionDef,
  Ticket,
  StartJobPayload,
  JobHandle,
  RuntimePhase,
  AccountLane,
  AccountStatus,
} from './types'
import { MODES } from './constants'

// ── helpers ──

let _seq = 0
function uid(prefix = 'id'): string {
  return `${prefix}_${Date.now()}_${++_seq}_${Math.random().toString(36).slice(2, 8)}`
}

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

function randInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

// ── data pools ──

const SURNAMES = ['张', '李', '王', '刘', '陈', '杨', '赵', '黄', '周', '吴', '徐', '孙', '马', '朱', '胡', '郭', '何', '高', '林', '罗']
const GIVEN_NAMES = ['伟', '芳', '娜', '秀英', '敏', '静', '丽', '强', '磊', '军', '洋', '勇', '艳', '杰', '娟', '涛', '明', '超', '秀兰', '华']

const COURSE_NAMES = [
  '大学英语(四)', '高等数学A', '马克思主义基本原理',
  'Python程序设计', '数据结构与算法', '计算机网络',
  '大学物理', '中国近现代史纲要', '线性代数',
  '概率论与数理统计', '操作系统', '数据库原理',
  '软件工程', '编译原理', '计算机组成原理',
  '数字电路与逻辑设计', '毛泽东思想和中国特色社会主义理论体系概论',
  '思想道德与法治', '形势与政策', '体育(二)',
  '大学语文', 'C语言程序设计', 'Java程序设计',
  '人工智能导论', '机器学习', 'Web前端开发',
]

const TEACHERS = [
  '王教授', '李老师', '张教授', '刘老师', '陈教授',
  '杨老师', '赵教授', '黄老师', '周教授', '吴老师',
  '郑教授', '孙老师', '钱教授', '马老师',
]

const CHAPTER_TEMPLATES: Record<string, { chapters: string[]; sections: Record<string, string[]> }> = {
  _default: {
    chapters: ['第一章', '第二章', '第三章', '第四章', '第五章', '第六章'],
    sections: {
      '第一章': ['基本概念', '发展历史', '应用领域', '本章小结'],
      '第二章': ['核心理论', '数学模型', '分析方法', '案例研究'],
      '第三章': ['关键技术', '实现方案', '性能优化', '实践练习'],
      '第四章': ['进阶内容', '综合应用', '前沿动态', '复习题'],
      '第五章': ['专题讨论', '项目实战', '扩展阅读', '自测题'],
      '第六章': ['总复习', '模拟考试', '答疑', '课程总结'],
    },
  },
}

// ── generators ──

export function generateMockAccounts(count = 8): Account[] {
  const accounts: Account[] = []
  const statuses: AccountStatus[] = ['online', 'online', 'online', 'online', 'online', 'offline', 'error', 'checking']

  for (let i = 0; i < count; i++) {
    const phone = `1${randInt(30, 99)}${String(randInt(1000, 9999))}${String(randInt(1000, 9999))}`
    const name = pick(SURNAMES) + pick(GIVEN_NAMES)
    accounts.push({
      id: uid('acct'),
      username: phone,
      displayName: name,
      status: i < statuses.length ? statuses[i] : 'online',
      lastChecked: Date.now() - randInt(0, 3600000),
      errorMessage: i === 6 ? '登录凭证已过期，请重新登录' : undefined,
    })
  }
  return accounts
}

export function generateMockCoursesForAccount(accountId: string, count?: number): Course[] {
  const n = count ?? randInt(4, 10)
  const courses: Course[] = []
  const used = new Set<number>()

  for (let i = 0; i < n; i++) {
    let idx: number
    do { idx = randInt(0, COURSE_NAMES.length - 1) } while (used.has(idx) && used.size < COURSE_NAMES.length)
    used.add(idx)

    const totalSections = randInt(8, 36)
    const completedSections = randInt(0, totalSections)
    const progress = Math.round((completedSections / totalSections) * 100)

    courses.push({
      id: uid('course'),
      name: COURSE_NAMES[idx],
      teacher: pick(TEACHERS),
      coverUrl: undefined,
      progress,
      totalSections,
      completedSections,
      accountId,
      url: `https://mooc1.chaoxing.com/course/${uid('')}.html`,
    })
  }
  return courses
}

export function generateMockSections(_courseId: string): SectionDef[] {
  const chapterCount = randInt(3, 7)
  const chapters: SectionDef[] = []

  for (let i = 0; i < chapterCount; i++) {
    const chapterName = `第${i + 1}章 ${pick(['函数与极限', '导数与微分', '积分学', '线性方程组', '概率基础', '数据结构基础', '网络协议', '算法设计'])}`
    const sectionCount = randInt(2, 5)
    const children: SectionDef[] = []

    for (let j = 0; j < sectionCount; j++) {
      const type = pick<'chapter' | 'section' | 'quiz' | 'video' | 'doc'>(['section', 'section', 'video', 'quiz', 'doc'])
      children.push({
        id: uid('sec'),
        name: `${i + 1}.${j + 1} ${pick(['基本概念', '核心内容', '例题讲解', '课后练习', '拓展阅读', '视频讲解', '单元测验', '讨论题'])}`,
        parentId: undefined,
        completed: Math.random() > 0.5,
        type,
        duration: type === 'video' ? randInt(300, 3600) : type === 'quiz' ? randInt(120, 900) : undefined,
      })
    }

    chapters.push({
      id: uid('ch'),
      name: chapterName,
      completed: children.every((c) => c.completed),
      type: 'chapter',
      children,
    })
  }
  return chapters
}

export function generateMockTickets(count?: number): Ticket[] {
  const n = count ?? randInt(3, 8)
  const templates = [
    { title: '登录验证码需要手动处理', message: '账号 138****5678 登录时出现图形验证码，需要人工完成验证。', severity: 'warning' as const },
    { title: '课程进度异常', message: '课程"大学英语(四)"已完成章节数与服务器记录不匹配，建议重新扫描。', severity: 'warning' as const },
    { title: '视频播放速度警告', message: '课程"高等数学A"的视频播放速度超过平台限制，可能被检测为异常行为。', severity: 'critical' as const },
    { title: '账号登录状态失效', message: '账号 159****2345 的登录Cookie已过期，需要重新登录。', severity: 'critical' as const },
    { title: '测验答案置信度低', message: '"Python程序设计"第3章测验中的2道题目AI置信度低于60%，建议人工复核。', severity: 'info' as const },
    { title: '任务队列堆积', message: '当前有5个任务等待执行超过10分钟，建议增加并发数或检查账号状态。', severity: 'warning' as const },
    { title: '每日任务完成', message: '今日所有计划任务已执行完毕，共完成12门课程的32个章节学习。', severity: 'info' as const },
    { title: '新课程检测到', message: '账号 177****8901 检测到2门新课程："大学语文"和"形势与政策"，已自动添加到课程列表。', severity: 'info' as const },
  ]

  return templates.slice(0, n).map((t) => ({
    id: uid('ticket'),
    title: t.title,
    message: t.message,
    severity: t.severity,
    resolved: Math.random() > 0.6,
    resolvedAt: Math.random() > 0.6 ? Date.now() - randInt(0, 86400000) : undefined,
    resolution: Math.random() > 0.6 ? '已手动处理完成' : undefined,
    createdAt: Date.now() - randInt(0, 86400000),
  }))
}

export function generateMockJobHandle(
  payload: StartJobPayload,
  existingPhases?: RuntimePhase[],
): JobHandle {
  const modeConfig = MODES.find((m) => m.key === payload.mode) ?? MODES[4] // default full-auto

  const phases: RuntimePhase[] = existingPhases ?? modeConfig.phases.map(([name, msg], idx) => ({
    name,
    status: idx === 0 ? 'running' as const : 'pending' as const,
    progress: idx === 0 ? randInt(5, 15) : 0,
    message: msg,
  }))

  const maxConcurrency = (payload.options?.maxConcurrency as number) ?? 2
  const lanes: AccountLane[] = payload.accounts.map((acctId, i) => ({
    accountId: acctId,
    status: i < maxConcurrency ? 'running' as const : 'pending' as const,
    progress: i < maxConcurrency ? randInt(5, 20) : 0,
    currentTask: i < maxConcurrency ? '正在初始化...' : '等待中...',
    currentPhase: i < maxConcurrency ? (modeConfig?.phases[0]?.[0] ?? '初始化') : undefined,
    startedAt: i < maxConcurrency ? Date.now() : undefined,
  }))

  return {
    jobId: uid('job'),
    status: 'running',
    createdAt: Date.now(),
    startedAt: Date.now(),
    objective: payload.objective,
    strategy: payload.strategy,
    mode: payload.mode,
    courseCount: payload.courses.length,
    accountCount: payload.accounts.length,
    progress: 0,
    phaseIndex: 0,
    phases,
    lanes,
  }
}

export { sleep }
