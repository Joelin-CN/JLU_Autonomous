<template>
  <div class="settings">
    <h2 class="settings__title">系统设置</h2>
    <p class="settings__sub">配置 AI 推理、账号、运行预算与界面主题</p>

    <!-- ── AI 推理 ── -->
    <GlassmorphicPanel class="panel" padding="22px">
      <h3 class="panel__title">AI 推理 · {{ aiStatus.label || '火山方舟（豆包）' }}</h3>
      <div class="ai-status">
        <select
          class="field__input"
          style="max-width: 180px"
          :value="aiStatus.provider"
          @change="switchAiProvider(($event.target as HTMLSelectElement).value)"
        >
          <option value="doubao-api">火山方舟（豆包）</option>
          <option value="deepseek-api">DeepSeek</option>
        </select>
        <Chip :variant="aiStatus.configured ? 'ok' : 'warn'" size="md">
          {{ aiStatus.configured ? `已配置 ${aiStatus.keyTail}` : '未配置' }}
        </Chip>
        <span class="ai-model">模型 {{ aiStatus.model || '—' }}</span>
      </div>
      <div class="panel__grid">
        <div class="field">
          <label class="field__label">API Key</label>
          <p class="field__hint">{{ aiKeyHint }}</p>
          <MaskedInput
            v-model="aiKey"
            :placeholder="aiStatus.configured ? '已配置，留空保持不变' : aiKeyPlaceholder"
          />
        </div>
        <div class="field">
          <label class="field__label">模型 ID</label>
          <p class="field__hint">方舟接入点 ID（ep- 或模型名）</p>
          <input
            v-model="aiModel"
            type="text"
            class="field__input"
            placeholder="ep-…"
          />
        </div>
        <div class="field">
          <label class="field__label">答题重试次数</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.quizRetryCount"
            min="0"
            max="10"
            @change="settingsStore.updateSetting('quizRetryCount', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field">
          <label class="field__label">目标正确率 (%)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.targetAccuracy"
            min="60"
            max="100"
            @change="settingsStore.updateSetting('targetAccuracy', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>
      <div class="panel__actions">
        <button class="btn-primary" :disabled="busy" @click="saveAi">
          {{ aiSaving ? '保存中…' : '保存并写入本地文件' }}
        </button>
        <button class="btn-ghost" :disabled="busy" @click="testAi">
          {{ aiTesting ? '测试中…' : '测试连通性' }}
        </button>
        <span class="ai-result" :class="{ 'ai-result--ok': aiTestOk }">{{ aiTestMsg }}</span>
      </div>
    </GlassmorphicPanel>

    <!-- ── 账号管理 ── -->
    <GlassmorphicPanel class="panel" padding="22px">
      <h3 class="panel__title">账号管理</h3>
      <FilePickerField
        v-model="accountsFilePath"
        label="当前账号文件"
        :default-path="defaultAccountsPath"
      />
      <p v-if="accountsError" class="field__error">{{ accountsError }}</p>
      <div v-if="accountStore.accounts.length" class="creds-table">
        <div class="creds-row creds-row--head">
          <span class="creds-cell">#</span>
          <span class="creds-cell">账号</span>
          <span class="creds-cell">登录网址</span>
          <span class="creds-cell">操作</span>
        </div>
        <div v-for="(acc, i) in accountStore.accounts" :key="acc.id" class="creds-row">
          <span class="creds-cell creds-cell--muted">{{ i + 1 }}</span>
          <span class="creds-cell creds-cell--mono">{{ maskPhone(acc.username) }}</span>
          <span class="creds-cell creds-cell--muted">{{ websiteLabel(acc.website) }}</span>
          <span class="creds-cell">
            <button class="btn-link" :disabled="busy" @click="openEdit(acc)">编辑</button>
            <button class="btn-link btn-link--danger" :disabled="busy" @click="askDelete(acc)">
              删除
            </button>
          </span>
        </div>
      </div>
      <div v-else class="creds-empty">添加第一个账号</div>
      <div class="panel__actions">
        <button class="btn-primary" :disabled="busy" @click="openAdd">添加账号</button>
        <span class="field__hint">{{ busy ? '任务运行中不可修改账号' : '账号修改即时生效' }}</span>
      </div>
    </GlassmorphicPanel>

    <!-- ── 浏览器与系统 ── -->
    <GlassmorphicPanel class="panel" padding="22px">
      <h3 class="panel__title">浏览器与系统</h3>
      <div class="panel__grid">
        <div class="field">
          <label class="field__label">Python 路径</label>
          <p class="field__hint">留空使用系统 PATH 中的 python；推荐指向含 openai 的环境</p>
          <input
            type="text"
            class="field__input field__input--wide"
            :value="settingsStore.settings.pythonPath"
            placeholder="python"
            @change="onPythonPathChange(($event.target as HTMLInputElement).value)"
          />
          <p v-if="pythonPathFeedback" :class="pythonPathFeedback.ok ? 'field__hint' : 'field__error'">
            {{ pythonPathFeedback.text }}
          </p>
        </div>
        <div class="field">
          <label class="field__label">页面加载超时 (秒)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.pageLoadTimeout"
            min="5"
            max="120"
            @change="settingsStore.updateSetting('pageLoadTimeout', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field">
          <label class="field__label">快照超时 (秒)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.snapshotTimeout"
            min="5"
            max="60"
            @change="settingsStore.updateSetting('snapshotTimeout', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field">
          <label class="field__label">点击超时 (秒)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.clickTimeout"
            min="1"
            max="30"
            @change="settingsStore.updateSetting('clickTimeout', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field">
          <label class="field__label">视频观看超时 (秒)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.videoWatchTimeout"
            min="10"
            max="600"
            @change="settingsStore.updateSetting('videoWatchTimeout', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field">
          <label class="field__label">答题超时 (秒)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.quizAnswerTimeout"
            min="30"
            max="600"
            @change="settingsStore.updateSetting('quizAnswerTimeout', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field">
          <label class="field__label">章节完成超时 (秒)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.sectionCompleteTimeout"
            min="5"
            max="120"
            @change="settingsStore.updateSetting('sectionCompleteTimeout', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field">
          <label class="field__label">日志保留 (天)</label>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.logRetention"
            min="1"
            max="30"
            @change="settingsStore.updateSetting('logRetention', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="field field--row">
          <div class="field__info">
            <label class="field__label">无头模式</label>
            <p class="field__hint">浏览器在后台运行，不显示窗口</p>
          </div>
          <Toggle
            :model-value="settingsStore.settings.headless"
            @update:model-value="settingsStore.updateSetting('headless', $event)"
          />
        </div>
        <div class="field field--row">
          <div class="field__info">
            <label class="field__label">系统通知</label>
            <p class="field__hint">任务完成或异常时推送桌面通知</p>
          </div>
          <Toggle
            :model-value="settingsStore.settings.notifications"
            @update:model-value="settingsStore.updateSetting('notifications', $event)"
          />
        </div>
      </div>
    </GlassmorphicPanel>

    <!-- ── 运行与内存 ── -->
    <GlassmorphicPanel class="panel" padding="22px">
      <h3 class="panel__title">运行与内存</h3>
      <BudgetGauge
        :plan="memoryStore.plan"
        :project-chrome-gb="memoryStore.latest?.projectChromeGB ?? 0"
        :remaining-count="memoryStore.latest?.remainingCount ?? memoryStore.plan?.maxConcurrent ?? null"
        :mock="mockMode"
      />
      <div class="panel__grid">
        <div class="field">
          <label class="field__label">目标并发</label>
          <p class="field__hint">自动上限 {{ planMax }}（内存与 CPU 取较小值）</p>
          <input
            type="range"
            min="1"
            :max="planMax"
            :value="concurrencyTarget ?? planMax"
            class="field__range"
            @input="setConcurrency(Number(($event.target as HTMLInputElement).value))"
          />
          <span class="field__hint">当前：{{ concurrencyTarget ?? '自动（上限）' }}</span>
        </div>
        <div class="field">
          <label class="field__label">单实例估算 (GB)</label>
          <p class="field__hint">实测约 0.5–0.55，默认 0.7 留余量</p>
          <input
            type="number"
            class="field__input"
            :value="settingsStore.settings.perAccountEstimateGB"
            min="0.3"
            max="4"
            step="0.1"
            @change="settingsStore.updateSetting('perAccountEstimateGB', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>
    </GlassmorphicPanel>

    <!-- ── 账号编辑弹窗 ── -->
    <div v-if="editing" class="modal-mask" @click.self="closeEdit">
      <div class="modal" role="dialog" aria-modal="true">
        <h3 class="modal__title">{{ editing.id !== null ? '编辑账号' : '添加账号' }}</h3>
        <div class="modal__body">
          <div class="field">
            <label class="field__label">账号</label>
            <input v-model="form.account" type="text" class="field__input" :disabled="editing.id !== null" />
          </div>
          <div class="field">
            <label class="field__label">密码</label>
            <MaskedInput v-model="form.password" placeholder="请输入密码" />
          </div>
          <div class="field">
            <label class="field__label">登录网址（可选）</label>
            <input v-model="form.website" type="text" class="field__input" placeholder="留空使用默认登录页" />
          </div>
        </div>
        <div class="modal__actions">
          <button class="btn-primary" :disabled="busy" @click="submitAccount">保存</button>
          <button class="btn-ghost" @click="closeEdit">取消</button>
          <span class="field__error">{{ formError }}</span>
        </div>
      </div>
    </div>

    <ConfirmDialog
      :open="deleting !== null"
      title="删除账号"
      :message="`确定删除账号 ${deleting ? maskPhone(deleting.username) : ''}？登录档案目录不会被删除。`"
      @confirm="confirmDelete"
      @cancel="deleting = null"
    />

    <!-- ── Theme ── -->
    <GlassmorphicPanel class="panel" padding="22px">
      <h3 class="panel__title">界面主题</h3>
      <div class="theme-row">
        <div class="field__info">
          <label class="field__label">主题模式</label>
          <p class="field__hint">切换浅色 / 深色界面风格</p>
        </div>
        <div class="theme-switch">
          <PillButton
            :active="settingsStore.settings.theme === 'light'"
            variant="default"
            @click="settingsStore.setTheme('light')"
          >☀️ 浅色</PillButton>
          <PillButton
            :active="settingsStore.settings.theme === 'dark'"
            variant="default"
            @click="settingsStore.setTheme('dark')"
          >🌙 深色</PillButton>
        </div>
      </div>
      <button class="btn-reset" @click="settingsStore.resetSettings()">恢复默认设置</button>
    </GlassmorphicPanel>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import GlassmorphicPanel from '@/shared/ui/GlassmorphicPanel.vue'
import StatusDot from '@/shared/ui/StatusDot.vue'
import Toggle from '@/shared/ui/Toggle.vue'
import PillButton from '@/shared/ui/PillButton.vue'
import Chip from '@/shared/ui/Chip.vue'
import MaskedInput from '@/shared/ui/MaskedInput.vue'
import BudgetGauge from '@/shared/ui/BudgetGauge.vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import FilePickerField from '@/shared/ui/FilePickerField.vue'
import { useSettingsStore } from '@/app/stores/settings.store'
import { useAccountStore } from '@/app/stores/account.store'
import { useMemoryStore } from '@/app/stores/memory.store'
import { useExecutionStore } from '@/app/stores/execution.store'
import { useLogStore } from '@/app/stores/log.store'
import { createApiClient, isMockMode } from '@/shared/lib/apiClient'
import type { Account } from '@/shared/lib/types'

const settingsStore = useSettingsStore()
const accountStore = useAccountStore()
const memoryStore = useMemoryStore()
const executionStore = useExecutionStore()
const logStore = useLogStore()
const api = createApiClient()

const mockMode = isMockMode()
const busy = computed(() => executionStore.isRunning)

const aiStatus = ref<{ provider: string; label: string; configured: boolean; model: string; keyTail: string }>({
  provider: 'doubao-api', label: '火山方舟（豆包）',
  configured: false, model: '', keyTail: '',
})

const aiKeyHint = computed(() =>
  aiStatus.value.provider === 'deepseek-api'
    ? 'DeepSeek API Key（sk- 开头）' : '火山方舟 ARK API Key（ark- 开头）')
const aiKeyPlaceholder = computed(() =>
  aiStatus.value.provider === 'deepseek-api' ? 'sk-…' : 'ark-…')
const aiKey = ref('')
const aiModel = ref('')
const aiSaving = ref(false)
const aiTesting = ref(false)
const aiTestMsg = ref('')
const aiTestOk = ref(false)

const accountsFilePath = ref(settingsStore.settings.accountsFilePath)
const accountsError = ref('')
const defaultAccountsPath = ref('')
let planTimer: ReturnType<typeof setInterval> | null = null

const editing = ref<{ id: number | null } | null>(null)
const deleting = ref<Account | null>(null)
const form = ref({ account: '', password: '', website: '' })
const formError = ref('')

// Inline validation for the Python path: checked while the user edits so a
// broken path never silently saves (SETTINGS_SET also hard-rejects it).
const pythonPathFeedback = ref<{ ok: boolean; text: string } | null>(null)

async function onPythonPathChange(value: string): Promise<void> {
  const trimmed = value.trim()
  pythonPathFeedback.value = null
  if (!trimmed) {
    settingsStore.updateSetting('pythonPath', '')
    return
  }
  try {
    const { reason } = await api.validatePython(trimmed)
    if (reason) {
      pythonPathFeedback.value = { ok: false, text: `✗ ${reason}` }
      return // don't persist an invalid path
    }
    pythonPathFeedback.value = { ok: true, text: '✓ 解释器可用' }
    settingsStore.updateSetting('pythonPath', trimmed)
  } catch (e: any) {
    pythonPathFeedback.value = { ok: false, text: `校验失败：${e?.message ?? '未知错误'}` }
  }
}

const planMax = computed(() => memoryStore.plan?.maxConcurrent ?? 8)
const concurrencyTarget = computed(() => settingsStore.settings.concurrencyTarget)

watch(accountsFilePath, (val) => {
  settingsStore.updateSetting('accountsFilePath', val)
  if (val) logStore.addLog('info', `账号文件已切换：${val}`, '设置')
  else logStore.addLog('info', '账号文件已恢复默认路径', '设置')
  reloadAccounts()
})

watch(() => settingsStore.settings.accountsFilePath, (val) => {
  // Keep the label in sync when the effective file changes through settings
  // (e.g. a previously saved override), not only via the file picker.
  if ((val ?? '') !== accountsFilePath.value) {
    accountsFilePath.value = val ?? ''
  }
})

watch(() => settingsStore.settings.perAccountEstimateGB, () => {
  memoryStore.refreshPlan()
})

onMounted(async () => {
  try {
    aiStatus.value = await api.getAiStatus()
    aiModel.value = aiStatus.value.model
  } catch { /* backend unavailable */ }
  try {
    defaultAccountsPath.value = await api.getAccountsDefaultPath()
  } catch { /* backend unavailable */ }
  await memoryStore.refreshPlan()
  planTimer = setInterval(async () => {
    if (!executionStore.isRunning) await memoryStore.refreshPlan()
  }, 5000)
  reloadAccounts()
})

onUnmounted(() => {
  if (planTimer) clearInterval(planTimer)
})

async function reloadAccounts(): Promise<void> {
  accountsError.value = ''
  try {
    await accountStore.refreshAccounts()
    // The backend owns the *effective* accounts file (set via settings IPC
    // or the file picker). Re-read it so the label matches what list/add/edit
    // actually used, even when the renderer store was not the writer.
    try {
      const backend = await api.getSettings()
      const effective = backend.accountsFilePath ?? ''
      if (effective !== accountsFilePath.value) {
        accountsFilePath.value = effective
        settingsStore.updateSetting('accountsFilePath', effective)
      }
    } catch {
      // backend unavailable — keep the current local value
    }
  } catch (e: any) {
    accountsError.value = e?.message ?? '账号文件解析失败'
  }
}

function websiteLabel(website?: string): string {
  if (!website) return '默认'
  if (website.includes('passport2.chaoxing.com/login') && website.includes('fid=')) {
    return '默认'
  }
  return website.replace(/^https?:\/\//, '').split('/')[0] || '默认'
}

async function switchAiProvider(provider: string): Promise<void> {
  if (provider === aiStatus.value.provider) return
  aiTestMsg.value = ''
  try {
    await api.setAiConfig({ provider, model: '' })
    aiStatus.value = await api.getAiStatus()
    aiModel.value = aiStatus.value.model
    aiKey.value = ''
    logStore.addLog('info', `AI 引擎已切换：${aiStatus.value.label}`, '设置')
  } catch (e: any) {
    aiTestMsg.value = e?.message ?? '切换失败'
    aiTestOk.value = false
  }
}

async function saveAi(): Promise<void> {
  aiSaving.value = true
  aiTestMsg.value = ''
  try {
    await api.setAiConfig({ provider: aiStatus.value.provider, apiKey: aiKey.value, model: aiModel.value })
    aiTestMsg.value = '已保存'
    aiTestOk.value = true
    logStore.addLog('info', 'AI 配置已保存到本地文件（密钥未回显）。', '设置')
    aiKey.value = ''
    aiStatus.value = await api.getAiStatus()
  } catch (e: any) {
    aiTestMsg.value = e?.message ?? '保存失败'
    aiTestOk.value = false
    logStore.addLog('error', `AI 配置保存失败：${e?.message ?? '未知错误'}`, '设置')
  } finally {
    aiSaving.value = false
  }
}

async function testAi(): Promise<void> {
  aiTesting.value = true
  aiTestMsg.value = ''
  try {
    const r = await api.testAi(aiStatus.value.provider)
    aiTestOk.value = r.ok
    aiTestMsg.value = r.ok ? '连通性正常' : (r.reason ?? '连接失败')
    logStore.addLog(r.ok ? 'info' : 'warn',
      r.ok ? '火山方舟连通性正常。' : `连通性测试失败：${r.reason ?? '未知原因'}`,
      '设置')
  } catch (e: any) {
    aiTestOk.value = false
    aiTestMsg.value = e?.message ?? '连接失败'
    logStore.addLog('error', `连通性测试失败：${e?.message ?? '未知错误'}`, '设置')
  } finally {
    aiTesting.value = false
  }
}

function maskPhone(phone: string): string {
  if (phone.length <= 4) return phone
  if (phone.length <= 7) return phone.slice(0, 3) + '****'
  return phone.slice(0, 3) + '****' + phone.slice(-4)
}

function openAdd(): void {
  editing.value = { id: null }
  form.value = { account: '', password: '', website: '' }
  formError.value = ''
}

function openEdit(acc: Account): void {
  editing.value = { id: Number(acc.id) }
  form.value = { account: acc.username, password: '', website: '' }
  formError.value = ''
}

function closeEdit(): void {
  editing.value = null
}

function askDelete(acc: Account): void {
  deleting.value = acc
}

async function submitAccount(): Promise<void> {
  formError.value = ''
  try {
    if (editing.value?.id === null) {
      if (!form.value.account.trim() || !form.value.password) {
        formError.value = '账号与密码不能为空。'
        return
      }
      await accountStore.addAccount({
        account: form.value.account.trim(),
        password: form.value.password,
        website: form.value.website.trim() || undefined,
      })
      logStore.addLog('info', '账号已添加。', '设置')
    } else if (editing.value) {
      await accountStore.editAccount({
        index: editing.value.id,
        password: form.value.password || undefined,
        website: form.value.website.trim() || undefined,
      })
      logStore.addLog('info', `账号 ${editing.value.id} 已更新。`, '设置')
    }
    closeEdit()
    await reloadAccounts()
  } catch (e: any) {
    formError.value = e?.message ?? '保存失败'
    logStore.addLog('error', `账号保存失败：${e?.message ?? '未知错误'}`, '设置')
  }
}

async function confirmDelete(): Promise<void> {
  if (deleting.value === null) return
  try {
    await accountStore.removeAccount(Number(deleting.value.id))
    logStore.addLog('info', `已删除账号 ${maskPhone(deleting.value.username)}。`, '设置')
  } catch (e: any) {
    accountsError.value = e?.message ?? '删除失败'
    logStore.addLog('error', `账号删除失败：${e?.message ?? '未知错误'}`, '设置')
  }
  deleting.value = null
  await reloadAccounts()
}

function setConcurrency(value: number): void {
  settingsStore.updateSetting('concurrencyTarget', value)
}
</script>

<style scoped>
.settings {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 40px;
}
.settings__title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
}
.settings__sub {
  font-size: 14px;
  color: var(--muted);
  margin-top: -12px;
}
.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel__title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}
.panel__grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.panel__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ai-status {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ai-model {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
}
.ai-result { font-size: 12px; color: var(--warn); }
.ai-result--ok { color: var(--ok); }
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field--row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}
.field__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.field__hint {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
}
.field__error {
  font-size: 12px;
  color: var(--warn);
}
.field__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.field__input {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 14px;
  outline: none;
  max-width: 320px;
}
.field__input--wide {
  max-width: 520px;
}
.field__input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.field__range {
  width: 100%;
  max-width: 320px;
}
.btn-primary,
.btn-ghost {
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: 13px;
  cursor: pointer;
}
.btn-primary {
  border: none;
  background: var(--accent);
  color: #fff;
}
.btn-primary:disabled,
.btn-ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-ghost {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text);
}
.creds-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.creds-row {
  display: grid;
  grid-template-columns: 40px 1fr 1fr 140px;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.creds-row--head {
  font-weight: 700;
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--line);
  margin-bottom: 2px;
}
.creds-row:not(.creds-row--head):hover {
  background: var(--accent-soft);
}
.creds-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
}
.creds-cell--muted { color: var(--muted); }
.creds-cell--mono { font-family: var(--font-mono); font-size: 12px; }
.creds-empty {
  font-size: 13px;
  color: var(--muted);
  text-align: center;
  padding: 20px 0;
}
.btn-link {
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
.btn-link--danger { color: var(--warn); }
.btn-reset {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font-family: var(--font-ui);
  font-size: 12px;
  cursor: pointer;
}
.theme-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.theme-switch {
  display: flex;
  gap: 8px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.modal {
  width: 420px;
  max-width: calc(100vw - 40px);
  padding: 22px;
  border-radius: var(--radius);
  background: var(--bg);
  border: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.modal__title {
  font-family: var(--font-display);
  font-size: 16px;
  color: var(--text);
}
.modal__body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.modal__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
@media (max-width: 600px) {
  .panel__grid { grid-template-columns: 1fr; }
  .creds-row { grid-template-columns: 40px 1fr 1fr 80px; font-size: 12px; }
}
</style>
