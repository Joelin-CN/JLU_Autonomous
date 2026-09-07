<template>
  <ThemeProvider>
    <div class="app" :data-theme="settingsStore.settings.theme">
      <AppSidebar />
      <main class="main">
        <header class="header">
          <span class="header__title">超星助手</span>
          <span class="header__subtitle">智能学习辅助</span>
          <button
            v-if="logStore.collapsed"
            class="header__log-btn"
            title="显示日志控制台"
            @click="logStore.toggleCollapsed()"
          >
            📋 日志
            <span v-if="logStore.errorCount > 0" class="header__log-badge">{{ logStore.errorCount }}</span>
          </button>
        </header>
        <section class="content">
          <router-view />
        </section>
        <LogConsole v-if="!logStore.collapsed" />
      </main>
    </div>
    <CaptchaModal />
  </ThemeProvider>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import ThemeProvider from '@/shared/ui/ThemeProvider.vue'
import AppSidebar from '@/shared/ui/AppSidebar.vue'
import LogConsole from '@/shared/ui/LogConsole.vue'
import CaptchaModal from '@/shared/ui/CaptchaModal.vue'
import { useSettingsStore } from '@/app/stores/settings.store'
import { useLogStore } from '@/app/stores/log.store'
import { useAccountStore } from '@/app/stores/account.store'
import { useAttentionStore } from '@/app/stores/attention.store'

const settingsStore = useSettingsStore()
const logStore = useLogStore()
const accountStore = useAccountStore()
const attentionStore = useAttentionStore()

onMounted(() => {
  // Bootstrap initial data fetching (fire-and-forget)
  accountStore.fetchAccounts()
  attentionStore.fetchTickets()
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  width: 100%;
  height: 100%;
  overflow: hidden;
  font-family: var(--font-ui, sans-serif);
  background: var(--bg);
  color: var(--text);
}

.app {
  display: grid;
  grid-template-columns: 240px 1fr;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.header__title {
  font-family: var(--font-display, sans-serif);
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
}

.header__subtitle {
  font-size: 13px;
  color: var(--muted);
}

.header__log-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-family: var(--font-ui);
  font-size: 12px;
  color: var(--text);
  background: none;
  border: 1px solid var(--line);
  border-radius: 8px;
  cursor: pointer;
}

.header__log-btn:hover {
  background: var(--panel-hover, rgba(255, 255, 255, 0.06));
}

.header__log-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: var(--warn, #d9803a);
  border-radius: 8px;
}

.content {
  flex: 1;
  overflow: auto;
  padding: 24px;
}
</style>
