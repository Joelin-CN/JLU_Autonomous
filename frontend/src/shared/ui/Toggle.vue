<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    class="toggle"
    :class="{ 'toggle--on': modelValue, 'toggle--disabled': disabled }"
    @click="toggle"
  >
    <span class="toggle__thumb" />
  </button>
</template>

<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

function toggle() {
  if (!props.disabled) {
    emit('update:modelValue', !props.modelValue)
  }
}
</script>

<style scoped>
.toggle {
  position: relative;
  width: 40px;
  height: 22px;
  border-radius: 999px;
  border: none;
  cursor: pointer;
  background: var(--line);
  transition: background 0.25s ease;
  padding: 0;
  outline: none;
}

.toggle:focus-visible {
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.toggle--on {
  background: var(--accent);
}

.toggle--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.toggle__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.25s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.toggle--on .toggle__thumb {
  transform: translateX(18px);
}
</style>
