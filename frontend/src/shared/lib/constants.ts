import type {
  Objective,
  Strategy,
  ModeType,
  Settings,
  ObjectiveType,
} from './types'

export const OBJECTIVES: Objective[] = [
  {
    key: 'catchup',
    label: '赶进度',
    description: '快速完成所有未完成章节的学习任务',
    icon: '⚡',
  },
  {
    key: 'exam-sprint',
    label: '考前冲刺',
    description: '集中完成考试相关章节和测验题目',
    icon: '🎯',
  },
  {
    key: 'maintenance',
    label: '日常维护',
    description: '保持课程进度，完成日常任务',
    icon: '📋',
  },
  {
    key: 'custom',
    label: '自定义',
    description: '自由选择课程章节和执行策略',
    icon: '🔧',
  },
]

export const STRATEGIES: Strategy[] = [
  {
    key: 'balanced',
    label: '均衡模式',
    description: '各账号平均分配任务，稳定推进',
  },
  {
    key: 'careful',
    label: '谨慎模式',
    description: '降低操作频率，模拟人工行为，减少风险',
  },
  {
    key: 'overnight',
    label: '通宵模式',
    description: '最大化速度，适合无人值守批量处理',
  },
  {
    key: 'surgical',
    label: '精准模式',
    description: '只处理指定章节或测验，跳过其他内容',
  },
]

export const MODES: {
  key: ModeType
  label: string
  desc: string
  readOnly: boolean
  phases: [string, string][]
}[] = [
  {
    key: 'course-scan',
    label: '课程扫描',
    desc: '扫描所有课程的章节列表和基本信息',
    readOnly: true,
    phases: [
      ['扫描课程', '浏览课程列表'],
      ['解析章节', '分析章节结构'],
      ['汇总报告', '生成扫描报告'],
    ],
  },
  {
    key: 'section-scan',
    label: '章节扫描',
    desc: '深度扫描指定课程的章节内容和测验',
    readOnly: true,
    phases: [
      ['定位课程', '找到目标课程'],
      ['遍历章节', '逐章节读取内容'],
      ['识别测验', '检测章节中的测验'],
      ['汇总报告', '生成扫描报告'],
    ],
  },
  {
    key: 'single-exec',
    label: '单任务执行',
    desc: '执行单个指定的学习任务',
    readOnly: false,
    phases: [
      ['准备任务', '加载任务配置'],
      ['执行任务', '运行学习任务'],
      ['验证结果', '检查执行结果'],
    ],
  },
  {
    key: 'batch-exec',
    label: '批量执行',
    desc: '批量处理多个课程的学习任务',
    readOnly: false,
    phases: [
      ['准备批量', '加载批量配置'],
      ['分配任务', '分配各账号任务'],
      ['并行执行', '多账号同时执行'],
      ['汇总结果', '汇总执行结果'],
    ],
  },
  {
    key: 'full-auto',
    label: '全自动模式',
    desc: '全自动完成所有课程的所有任务',
    readOnly: false,
    phases: [
      ['扫描课程', '获取课程列表'],
      ['分析任务', '分析待完成任务'],
      ['智能分配', '智能分配执行计划'],
      ['自动执行', '自动执行所有任务'],
      ['生成报告', '生成完成报告'],
    ],
  },
  {
    key: 'dry-run',
    label: '模拟运行',
    desc: '模拟执行流程，不实际操作课程',
    readOnly: true,
    phases: [
      ['加载配置', '加载运行配置'],
      ['模拟流程', '模拟执行流程'],
      ['预估结果', '预估执行结果'],
    ],
  },
]

export const DEFAULT_SETTINGS: Settings = {
  theme: 'light',
  language: 'zh-CN',
  maxConcurrency: 2,
  quizSolver: 'doubao',
  quizRetryCount: 10,
  logRetention: 7,
  notifications: true,
  debugMode: false,
  headless: true,
  targetAccuracy: 100,
  accountsFilePaths: { chaoxing: '', zhihuishu: '' },
  concurrencyTarget: null,
  perAccountEstimateGB: 0.7,
  pythonPath: '',
  pageLoadTimeout: 30,
  snapshotTimeout: 15,
  clickTimeout: 10,
  videoWatchTimeout: 60,
  quizAnswerTimeout: 120,
  sectionCompleteTimeout: 15,
  dryRun: false,
}

