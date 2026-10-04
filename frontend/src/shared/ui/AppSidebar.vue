<template>
  <aside class="sidebar">
    <div class="sidebar__brand">
      <span class="sidebar__brand-icon">🎓</span>
      <div>
        <h1 class="sidebar__brand-title">JLU 学习助手</h1>
        <p class="sidebar__brand-sub">Study Assistant</p>
      </div>
    </div>

    <!-- 全局平台切换器：平台是一级维度，全应用共享 platformStore 状态 -->
    <div class="sidebar__platform" role="tablist" aria-label="课程平台">
      <button
        v-for="p in platformStore.platforms"
        :key="p"
        role="tab"
        :aria-selected="platformStore.currentPlatform === p"
        class="platform-tab"
        :class="{
          'platform-tab--active': platformStore.currentPlatform === p,
      }"
        :style="platformStore.currentPlatform === p ? { borderColor: metaFor(p).color, color: metaFor(p).color } : undefined"
        :title="`切换到${metaFor(p).label}`"
        @click="onSwitch(p)"
      >
        <span class="platform-tab__icon">{{ metaFor(p).icon }}</span>
        <span class="platform-tab__label">{{ metaFor(p).shortLabel }}</span>
        <span
          v-if="executionStore.isRunningOn(p)"
          class="platform-tab__running"
          title="该平台有任务运行中"
        />
      </button>
    </div>

    <nav class="sidebar__nav">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="sidebar__nav-item"
        :class="{ 'sidebar__nav-item--active': route.path === item.path }"
      >
        <span class="sidebar__nav-icon">{{ item.icon }}</span>
        <span class="sidebar__nav-label">{{ item.label }}</span>
        <span v-if="item.badge" class="sidebar__badge" />
      </router-link>
    </nav>

    <div class="sidebar__footer">
      <div
        v-for="p in platformStore.platforms"
        :key="p"
        class="sidebar__session"
        :title="sessionTitle(p)"
      >
        <StatusDot :status="sessionStatusFor(p)" size="sm" />
        <span class="sidebar__session-platform" :style="{ color: metaFor(p).color }">
          {{ metaFor(p).shortLabel }}
        </span>
        <span class="sidebar__session-text">{{ sessionLabelFor(p) }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import StatusDot from './StatusDot.vue'
import type { Platform } from '@/shared/lib/types'
import { usePlatformStore } from '@/app/stores/platform.store'
import { useAccountStore } from '@/app/stores/account.store'
import { useExecutionStore } from '@/app/stores/execution.store'

const route = useRoute()
const platformStore = usePlatformStore()
const accountStore = useAccountStore()
const executionStore = useExecutionStore()

interface NavItem {
  path: string
  icon: string
  label: string
  badge?: boolean
}

withDefaults(defineProps<{
  navItems?: NavItem[]
}>(), {
  navItems: () => [
    { path: '/dashboard', icon: '📊', label: '仪表盘' },
    { path: '/course-atlas', icon: '📚', label: '课程总览' },
    { path: '/execution-studio', icon: '▶️', label: '执行监控', badge: false },
    { path: '/attention-queue', icon: '🔔', label: '关注队列', badge: false },
    { path: '/settings', icon: '⚙️', label: '系统设置' },
  ],
})

function metaFor(platform: Platform) {
  return platformStore.metaFor(platform)
}

async function onSwitch(next: Platform): Promise<void> {
  // 任务按平台独立槽位运行（双平台并行），切换只是 UI 上下文切换——
  // 运行中允许切换；视图随 platform store 变化自动按桶取数。
  await platformStore.switchPlatform(next)
}

function sessionStatusFor(platform: Platform): 'online' | 'running' | 'idle' | 'error' {
  if (executionStore.isRunningOn(platform)) return 'running'
  const list = accountStore.accountsFor(platform)
  if (!list.length) return 'idle'
  return list.some((a) => a.status === 'error') ? 'error' : 'online'
}

function sessionLabelFor(platform: Platform): string {
  if (executionStore.isRunningOn(platform)) return '任务运行中'
  const list = accountStore.accountsFor(platform)
  if (!list.length) return '未配置账号'
  return `${list.length} 个账号`
}

function sessionTitle(platform: Platform): string {
  return `${metaFor(platform).label} · ${sessionLabelFor(platform)}`
}
</script>

<style scoped>
.sidebar {
  width: 220px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg2);
  border-right: 1px solid var(--line);
  font-family: var(--font-ui);
  user-select: none;
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 16px 16px;
}

.sidebar__brand-icon {
  font-size: 28px;
  line-height: 1;
}

.sidebar__brand-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 0.5px;
}

.sidebar__brand-sub {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 1px;
  text-transform: uppercase;
}

/* ── 平台切换器 ── */
.sidebar__platform {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin: 0 16px 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.platform-tab {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 6px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--panel, transparent);
  color: var(--muted);
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.platform-tab:hover:not(:disabled) {
  color: var(--text);
  background: var(--panel-hover, rgba(255, 255, 255, 0.06));
}

.platform-tab--active {
  background: var(--accent-soft);
}

.platform-tab--disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.platform-tab__icon {
  font-size: 14px;
  line-height: 1;
}

.platform-tab__running {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ok, #46a758);
  box-shadow: 0 0 0 2px var(--bg2);
}

.sidebar__nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 8px;
  gap: 2px;
  overflow-y: auto;
}

.sidebar__nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  color: var(--muted);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  border-left: 3px solid transparent;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.sidebar__nav-item:hover {
  background: var(--accent-soft);
  color: var(--text);
}

.sidebar__nav-item--active {
  background: var(--accent-soft);
  color: var(--accent);
  border-left-color: var(--accent);
}

.sidebar__nav-icon {
  font-size: 16px;
  width: 22px;
  text-align: center;
}

.sidebar__nav-label {
  flex: 1;
}

.sidebar__badge {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

.sidebar__footer {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}

.sidebar__session {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar__session-platform {
  font-size: 12px;
  font-weight: 600;
}

.sidebar__session-text {
  font-size: 12px;
  color: var(--muted);
}
</style>
