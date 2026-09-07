import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  ObjectiveType,
  StrategyType,
  ModeType,
} from '@/shared/lib/types'

export const useCampaignStore = defineStore('campaign', () => {
  const objective = ref<ObjectiveType>('catchup')
  const strategy = ref<StrategyType>('balanced')
  const mode = ref<ModeType>('full-auto')
  const selectedCourseIds = ref<string[]>([])
  const selectedOperatorIds = ref<string[]>([])
  const options = ref<Record<string, unknown>>({})

  /* computed */

  const isValid = computed(() =>
    selectedCourseIds.value.length > 0 &&
    selectedOperatorIds.value.length > 0
  )

  /* actions */

  function setObjective(val: ObjectiveType): void {
    objective.value = val
  }

  function setStrategy(val: StrategyType): void {
    strategy.value = val
  }

  function setMode(val: ModeType): void {
    mode.value = val
  }

  function setSelectedCourses(ids: string[]): void {
    selectedCourseIds.value = ids
  }

  function setSelectedOperators(ids: string[]): void {
    selectedOperatorIds.value = ids
  }

  function syncSelection(input: { courseIds: string[]; operatorIds: string[] }): void {
    selectedCourseIds.value = [...input.courseIds]
    selectedOperatorIds.value = [...input.operatorIds]
  }

  function setOption(key: string, value: unknown): void {
    options.value = { ...options.value, [key]: value }
  }

  function resetCampaign(): void {
    objective.value = 'catchup'
    strategy.value = 'balanced'
    mode.value = 'full-auto'
    selectedCourseIds.value = []
    selectedOperatorIds.value = []
    options.value = {}
  }

  return {
    objective,
    strategy,
    mode,
    selectedCourseIds,
    selectedOperatorIds,
    options,
    isValid,
    setObjective,
    setStrategy,
    setMode,
    setSelectedCourses,
    setSelectedOperators,
    syncSelection,
    setOption,
    resetCampaign,
  }
})
