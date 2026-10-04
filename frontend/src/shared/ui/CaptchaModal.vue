<template>
  <Teleport to="body">
    <div v-if="ticket" class="captcha-overlay" role="dialog" aria-modal="true" aria-labelledby="captcha-title">
      <div class="captcha-modal" :class="{ 'captcha-modal--qr': kind === 'qrcode' }">
        <header class="captcha-modal__head">
          <h2 id="captcha-title" class="captcha-modal__title">{{ ticket.title || defaultTitle }}</h2>
          <span :class="['captcha-modal__timer', { 'captcha-modal__timer--urgent': remainingMs <= 60_000 }]">
            ⏳ {{ formattedRemaining }}
          </span>
        </header>

        <p v-if="captchaStore.queueLength > 1" class="captcha-modal__queue">
          还有 {{ captchaStore.queueLength - 1 }} 个待处理
        </p>

        <!-- On a wrong-answer retry the backend sends a retry-specific message;
             render it in the alert style instead of the muted line (and skip the
             duplicate generic message). -->
        <p v-if="ticket.isRetry" class="captcha-modal__retry">{{ ticket.message }}</p>
        <p v-else-if="kind === 'hint'" class="captcha-modal__msg captcha-modal__msg--hint">
          <template v-for="(part, i) in messageParts" :key="i">
            <a v-if="part.url" :href="part.text" target="_blank" rel="noopener noreferrer">{{ part.text }}</a>
            <template v-else>{{ part.text }}</template>
          </template>
        </p>
        <p v-else class="captcha-modal__msg">{{ ticket.message }}</p>

        <!-- 输入型：验证码截图 + 文本输入 -->
        <div v-if="kind === 'captcha'" class="captcha-modal__image-wrap">
          <img
            v-if="ticket.imageBase64"
            :src="ticket.imageBase64"
            alt="验证码截图"
            class="captcha-modal__image"
          />
          <div v-else class="captcha-modal__image-missing">未提供验证码截图</div>
        </div>

        <!-- 扫码型：二维码大图（不做 pixelated，保持二维码锐利边缘由原图保证） -->
        <div v-else-if="kind === 'qrcode'" class="captcha-modal__qr-wrap">
          <img
            v-if="ticket.imageBase64"
            :src="ticket.imageBase64"
            alt="登录二维码"
            class="captcha-modal__qr"
          />
          <div v-else class="captcha-modal__image-missing">未提供二维码截图</div>
          <p class="captcha-modal__qr-hint">请使用{{ platformLabel }}手机端扫码登录，扫码成功后将自动继续</p>
        </div>

        <input
          v-if="kind === 'captcha'"
          ref="inputEl"
          v-model="answer"
          class="captcha-modal__input"
          type="text"
          autocomplete="off"
          spellcheck="false"
          placeholder="输入验证码"
          :disabled="expired"
          @keyup.enter="onSubmit"
        />

        <p v-if="expired" class="captcha-modal__expired">{{ expiredText }}</p>
        <p v-else-if="captchaStore.error" class="captcha-modal__error">{{ captchaStore.error }}</p>

        <footer class="captcha-modal__actions">
          <button
            class="captcha-modal__btn captcha-modal__btn--ghost"
            :disabled="submitting"
            @click="onSkip"
          >{{ skipLabel }}</button>
          <button
            v-if="kind === 'captcha'"
            class="captcha-modal__btn captcha-modal__btn--primary"
            :disabled="expired || submitting || !answer.trim()"
            @click="onSubmit"
          >{{ submitLabel }}</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { useCaptchaStore, ticketTimeoutMs } from '@/app/stores/captcha.store'
import { PLATFORM_META } from '@/shared/lib/platforms'

const captchaStore = useCaptchaStore()

const ticket = computed(() => captchaStore.current)
/** 工单交互形态：'captcha' 输入型 / 'qrcode' 扫码型 / 'hint' 提示型。 */
const kind = computed(() => ticket.value?.kind ?? 'captcha')

const answer = ref('')
const submitting = ref(false)
const inputEl = ref<HTMLInputElement | null>(null)

/* ── countdown ── */

// Tick a reactive "now" once per second; remaining time derives from it so the
// timer survives the component re-rendering for the next queued ticket.
const now = ref(Date.now())
let timerId: ReturnType<typeof setInterval> | null = null

function startTimer(): void {
  if (timerId !== null) return
  timerId = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopTimer(): void {
  if (timerId !== null) {
    clearInterval(timerId)
    timerId = null
  }
}

const remainingMs = computed(() => {
  const t = ticket.value
  if (!t) return 0
  const elapsed = now.value - t.createdAt
  return Math.max(0, ticketTimeoutMs(t) - elapsed)
})

const expired = computed(() => remainingMs.value <= 0)

const expiredText = computed(() =>
  kind.value === 'captcha' ? '已超时，该课程已自动跳过' : '已超时，本次登录已取消',
)

const formattedRemaining = computed(() => {
  const totalSec = Math.ceil(remainingMs.value / 1000)
  const mm = String(Math.floor(totalSec / 60)).padStart(2, '0')
  const ss = String(totalSec % 60).padStart(2, '0')
  return `${mm}:${ss}`
})

/* ── per-kind presentation ── */

const defaultTitle = computed(() =>
  kind.value === 'qrcode' ? '扫码登录' : kind.value === 'hint' ? '需要人工处理' : '需要人工输入验证码',
)

const platformLabel = computed(() =>
  PLATFORM_META[ticket.value?.platform ?? 'zhihuishu'].label,
)

/** Split the message into plain-text / URL segments so appeal links (course
 *  lock warnings, slider guidance) render as real anchors without v-html. */
const URL_PATTERN = /https?:\/\/[^\s）)】\]，,。]+/g
const messageParts = computed<Array<{ text: string; url?: boolean }>>(() => {
  const message = ticket.value?.message ?? ''
  const parts: Array<{ text: string; url?: boolean }> = []
  let last = 0
  for (const match of message.matchAll(URL_PATTERN)) {
    const index = match.index ?? 0
    if (index > last) parts.push({ text: message.slice(last, index) })
    parts.push({ text: match[0], url: true })
    last = index + match[0].length
  }
  if (last < message.length) parts.push({ text: message.slice(last) })
  return parts
})

/* ── labels (driven by backend-provided options when present) ── */

const submitLabel = computed(() => ticket.value?.options?.[0] ?? '提交')
const skipLabel = computed(() => {
  if (ticket.value?.options?.[1]) return ticket.value.options[1]
  return kind.value === 'captcha' ? '跳过此课程' : '取消等待'
})

/* ── lifecycle ── */

// Reset per-ticket state and focus the input whenever a new ticket surfaces.
watch(
  () => ticket.value?.id,
  async (id) => {
    answer.value = ''
    submitting.value = false
    if (id) {
      now.value = Date.now()
      startTimer()
      await nextTick()
      inputEl.value?.focus()
    } else {
      stopTimer()
    }
  },
  { immediate: true },
)

onBeforeUnmount(stopTimer)

/* ── actions ── */

async function onSubmit(): Promise<void> {
  const t = ticket.value
  if (!t || expired.value || submitting.value || !answer.value.trim()) return
  submitting.value = true
  await captchaStore.submitAnswer(t.id, answer.value.trim())
}

async function onSkip(): Promise<void> {
  const t = ticket.value
  if (!t || submitting.value) return
  submitting.value = true
  await captchaStore.skip(t.id)
}
</script>

<style scoped>
.captcha-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.captcha-modal {
  width: 360px;
  max-width: calc(100vw - 48px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 24px;
  border-radius: var(--radius-md, 12px);
  background: var(--panel, #1b1b1f);
  border: 1px solid var(--line, rgba(255, 255, 255, 0.1));
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.captcha-modal__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.captcha-modal__title {
  font-family: var(--font-display, sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}

.captcha-modal__timer {
  font-family: var(--font-mono, monospace);
  font-size: 14px;
  font-weight: 700;
  color: var(--muted);
  flex-shrink: 0;
}
.captcha-modal__timer--urgent {
  color: var(--warn, #e5484d);
}

.captcha-modal__queue {
  font-size: 12px;
  color: var(--gold, #d9a441);
}

.captcha-modal__retry {
  font-size: 12px;
  font-weight: 600;
  color: var(--warn, #e5484d);
  background: var(--warn-soft, rgba(229, 72, 77, 0.12));
  padding: 6px 10px;
  border-radius: var(--radius-sm, 8px);
}

.captcha-modal__msg {
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
}

.captcha-modal__msg--hint a {
  color: var(--accent, #4f7cff);
  word-break: break-all;
}

.captcha-modal__image-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
  padding: 8px;
  border-radius: var(--radius-sm, 8px);
  background: #fff;
}
.captcha-modal__image {
  max-width: 100%;
  max-height: 160px;
  image-rendering: pixelated;
}
.captcha-modal__image-missing {
  font-size: 12px;
  color: #888;
}

/* ── 扫码型 ── */
.captcha-modal--qr {
  width: 400px;
}

.captcha-modal__qr-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: var(--radius-sm, 8px);
  background: #fff;
}

.captcha-modal__qr {
  width: 240px;
  height: 240px;
  object-fit: contain;
}

.captcha-modal__qr-hint {
  font-size: 12px;
  line-height: 1.5;
  color: #555;
  text-align: center;
}

.captcha-modal__input {
  width: 100%;
  padding: 10px 14px;
  border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--line, rgba(255, 255, 255, 0.15));
  background: var(--bg, #0f0f12);
  color: var(--text);
  font-family: var(--font-mono, monospace);
  font-size: 18px;
  letter-spacing: 4px;
  text-align: center;
}

.captcha-modal__input:focus {
  outline: none;
  border-color: var(--accent, #4f7cff);
}

.captcha-modal__input:disabled {
  opacity: 0.5;
}

.captcha-modal__expired {
  font-size: 12px;
  color: var(--warn, #e5484d);
  text-align: center;
}
.captcha-modal__error {
  font-size: 12px;
  color: var(--warn, #e5484d);
}

.captcha-modal__actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.captcha-modal__btn {
  padding: 8px 18px;
  border-radius: var(--radius-sm, 8px);
  font-family: var(--font-ui, sans-serif);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s, background 0.15s;
}
.captcha-modal__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.captcha-modal__btn--ghost {
  background: none;
  border: 1px solid var(--line, rgba(255, 255, 255, 0.2));
  color: var(--text);
}
.captcha-modal__btn--ghost:not(:disabled):hover {
  background: var(--accent-soft, rgba(79, 124, 255, 0.12));
}
.captcha-modal__btn--primary {
  background: var(--accent, #4f7cff);
  border: 1px solid var(--accent, #4f7cff);
  color: #fff;
}
.captcha-modal__btn--primary:not(:disabled):hover {
  opacity: 0.88;
}
</style>
