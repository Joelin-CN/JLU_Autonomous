import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Ticket, TicketSeverity } from '@/shared/lib/types'
import { createApiClient } from '@/shared/lib/apiClient'

const api = createApiClient()

/** Maximum number of tickets to keep in memory — prevents unbounded growth
 *  that contributed to system memory pressure during long-running jobs. */
const MAX_TICKETS = 200

export const useAttentionStore = defineStore('attention', () => {
  const tickets = ref<Ticket[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<string | null>(null)
  const severityFilter = ref<TicketSeverity | 'all'>('all')
  let pendingFetch: Promise<void> | null = null

  /* computed */

  const unresolvedTickets = computed(() =>
    tickets.value.filter((t) => !t.resolved),
  )

  const criticalTickets = computed(() =>
    tickets.value.filter((t) => t.severity === 'critical' && !t.resolved),
  )

  const filteredTickets = computed(() => {
    if (severityFilter.value === 'all') return tickets.value
    return tickets.value.filter((t) => t.severity === severityFilter.value)
  })

  const unresolvedCount = computed(() => unresolvedTickets.value.length)

  /* actions */

  async function fetchTickets(): Promise<void> {
    if (loading.value && pendingFetch) return pendingFetch
    if (loaded.value) return

    loading.value = true
    error.value = null
    pendingFetch = (async () => {
      try {
        tickets.value = await api.getTickets()
        loaded.value = true
      } catch (e: any) {
        error.value = e?.message ?? 'Failed to fetch tickets'
      } finally {
        loading.value = false
        pendingFetch = null
      }
    })()

    return pendingFetch
  }

  async function resolveTicket(
    ticketId: string,
    resolution: string,
  ): Promise<void> {
    // Update local state first via an immutable array replace. The renderer is
    // the source of truth for tickets (real ones arrive over the event stream,
    // not from a backend store), so the UI must reflect the resolution
    // regardless of what the API call does. An immutable replace also guarantees
    // the `tickets` ref triggers its computed dependents — mutating a ticket's
    // `resolved` in place can no-op when the object is shared by reference with
    // the mock client and already carries the new value (Vue skips the trigger
    // when oldValue === newValue).
    const resolvedAt = Date.now()
    let found = false
    tickets.value = tickets.value.map((t) => {
      if (t.id !== ticketId) return t
      found = true
      return { ...t, resolved: true, resolvedAt, resolution }
    })
    if (!found) return

    // Best-effort persistence. The backend's tickets:resolve operates on an
    // in-memory array that event-stream tickets never populate, so a
    // "not found" here is expected and must not revert the local resolution.
    try {
      await api.resolveTicket(ticketId, resolution)
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to persist ticket resolution'
    }
  }

  function addTicket(ticket: Ticket): void {
    tickets.value.unshift(ticket)
    // Cap to prevent unbounded growth during long-running jobs
    if (tickets.value.length > MAX_TICKETS) {
      tickets.value = tickets.value.slice(0, MAX_TICKETS)
    }
    loaded.value = true
  }

  /** Insert a ticket, or merge into the existing one with the same id.
   *  Captcha follow-ups (resolved/timeout) reuse the original id, so merging
   *  keeps a single archive entry instead of stacking duplicates. */
  function upsertTicket(ticket: Ticket): void {
    const existing = tickets.value.find((t) => t.id === ticket.id)
    if (existing) {
      Object.assign(existing, ticket)
      return
    }
    addTicket(ticket)
  }

  function setSeverityFilter(severity: TicketSeverity | 'all'): void {
    severityFilter.value = severity
  }

  return {
    tickets,
    loading,
    loaded,
    error,
    severityFilter,
    unresolvedTickets,
    criticalTickets,
    filteredTickets,
    unresolvedCount,
    fetchTickets,
    resolveTicket,
    addTicket,
    upsertTicket,
    setSeverityFilter,
  }
})
