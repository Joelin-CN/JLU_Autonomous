<template>
  <div class="theme-provider">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useSettingsStore } from '@/app/stores/settings.store'
import { applyTheme } from '@/shared/lib/designTokens'

const settingsStore = useSettingsStore()

// Apply initial theme
applyTheme(settingsStore.settings.theme)

// React to theme changes from any source
watch(
  () => settingsStore.settings.theme,
  (theme) => {
    applyTheme(theme)
  },
)
</script>

<style scoped>
.theme-provider {
  width: 100%;
  height: 100%;
}
</style>
