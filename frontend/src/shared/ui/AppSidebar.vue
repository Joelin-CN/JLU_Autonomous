<template>
  <aside class="sidebar">
    <div class="sidebar__brand">
      <span class="sidebar__brand-icon">🎓</span>
      <div>
        <h1 class="sidebar__brand-title">超星助手</h1>
        <p class="sidebar__brand-sub">Automation</p>
      </div>
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
      <div class="sidebar__session">
        <StatusDot :status="sessionStatus" size="sm" />
        <span class="sidebar__session-text">{{ sessionLabel }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import StatusDot from './StatusDot.vue'

const route = useRoute()

interface NavItem {
  path: string
  icon: string
  label: string
  badge?: boolean
}

withDefaults(defineProps<{
  navItems?: NavItem[]
  sessionStatus?: 'online' | 'offline' | 'running' | 'idle' | 'error' | 'done'
  sessionLabel?: string
}>(), {
  sessionStatus: 'idle',
  sessionLabel: 'Idle',
  navItems: () => [
    { path: '/dashboard', icon: '📊', label: '仪表盘' },
    { path: '/course-atlas', icon: '📚', label: '课程总览' },
    { path: '/execution-studio', icon: '▶️', label: '执行监控', badge: false },
    { path: '/attention-queue', icon: '🔔', label: '关注队列', badge: false },
    { path: '/settings', icon: '⚙️', label: '系统设置' },
  ],
})
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
  border-bottom: 1px solid var(--line);
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
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}

.sidebar__session {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar__session-text {
  font-size: 12px;
  color: var(--muted);
}
</style>
