import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Ticket } from '@/shared/lib/types'
import { createApiClient } from '@/shared/lib/apiClient'

const api = createApiClient()

/** Backend hard timeout for manual captcha entry (handlers.py: 10 minutes). */
export const CAPTCHA_TIMEOUT_MS = 10 * 60 * 1000

/**
 * Holds captcha tickets that need a human to read the screenshot and type an
 * answer. Tickets are shown one at a time (FIFO) by CaptchaModal; resolving or
 * skipping the current one advances to the next.
 *
 * The backend blocks the affected account's browser session while it waits for
 * the answer (max 10 min), so this is a real-time interrupt, not a passive list.
 */
export const useCaptchaStore = defineStore('captcha', () => {
  /** Pending captcha tickets, oldest first. The head is shown in the modal. */
  const queue = ref<Ticket[]>([])
  const error = ref<string | null>(null)

  /** Ticket ids the user has answered but the backend hasn't resolved yet.
   *  If such an id is re-emitted (same id, new image), it means the answer was
   *  wrong — the backend refreshed the captcha and is asking again. */
  const awaitingResult = ref<Set<string>>(new Set())

  const current = computed<Ticket | null>(() => queue.value[0] ?? null)
  const queueLength = computed(() => queue.value.length)
  const hasPending = computed(() => queue.value.length > 0)

  /** Ingest a ticket coming off the onTicket stream. */
  function ingest(ticket: Ticket): void {
    if (ticket.kind !== 'captcha') return

    // A resolved/timeout ticket carries the same id as the original — drop it
    // from the queue (the backend has stopped waiting; the modal must close).
    if (ticket.resolved) {
      awaitingResult.value.delete(ticket.id)
      dismiss(ticket.id)
      return
    }

    // Wrong-answer retry: same id re-emitted after the user submitted. The
    // backend refreshed the captcha image (Chaoxing rerolls it on a miss), so
    // mark it a retry and let the modal swap the image + show a hint.
    const wasAnswered = awaitingResult.value.delete(ticket.id)

    // Already queued (e.g. backend re-emitted before the user acted): merge in
    // place so the freshest image/message wins instead of stacking duplicates.
    const existing = queue.value.find((t) => t.id === ticket.id)
    if (existing) {
      Object.assign(existing, ticket, { isRetry: wasAnswered || existing.isRetry })
      return
    }

    queue.value.push({ ...ticket, isRetry: wasAnswered })
  }

  /** Remove a ticket from the queue without notifying the backend. */
  function dismiss(ticketId: string): void {
    queue.value = queue.value.filter((t) => t.id !== ticketId)
  }

  function parseAccountId(ticket: Ticket): number {
    const id = Number(ticket.accountId)
    if (!Number.isInteger(id)) {
      throw new Error(`Captcha ticket ${ticket.id} has no valid accountId.`)
    }
    return id
  }

  /** Submit the typed answer for a ticket, then optimistically advance. */
  async function submitAnswer(ticketId: string, answer: string): Promise<void> {
    const ticket = queue.value.find((t) => t.id === ticketId)
    if (!ticket) return

    error.value = null
    // Optimistic close — release the user immediately. Mark the id as awaiting
    // a backend verdict: if it gets re-emitted (same id, new image) the answer
    // was wrong and the modal reopens in retry mode; a resolved event closes it.
    awaitingResult.value.add(ticketId)
    dismiss(ticketId)
    try {
      await api.resolveCaptcha({
        ticketId,
        accountId: parseAccountId(ticket),
        answer,
      })
    } catch (e: any) {
      awaitingResult.value.delete(ticketId)
      error.value = e?.message ?? 'Failed to submit captcha answer'
    }
  }

  /** Skip the current course for this account instead of answering. */
  async function skip(ticketId: string): Promise<void> {
    const ticket = queue.value.find((t) => t.id === ticketId)
    if (!ticket) return

    error.value = null
    awaitingResult.value.delete(ticketId)
    dismiss(ticketId)
    try {
      await api.resolveCaptcha({
        ticketId,
        accountId: parseAccountId(ticket),
        action: 'skip',
      })
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to skip captcha'
    }
  }

  return {
    queue,
    error,
    current,
    queueLength,
    hasPending,
    ingest,
    dismiss,
    submitAnswer,
    skip,
  }
})
