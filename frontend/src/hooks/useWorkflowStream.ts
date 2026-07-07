// frontend/src/hooks/useWorkflowStream.ts
import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/app'
import type { SseEvent } from '@/types'

const HEARTBEAT_INTERVAL_MS = 15_000
const MISSED_HEARTBEAT_THRESHOLD = 4

export function useWorkflowStream(taskId: string | null): void {
  const appendEvent    = useAppStore(s => s.appendEvent)
  const addKnownStage  = useAppStore(s => s.addKnownStage)
  const setApproval    = useAppStore(s => s.setApproval)
  const setCriteria    = useAppStore(s => s.setCriteria)
  const setFinalResult = useAppStore(s => s.setFinalResult)
  const setDisconnect  = useAppStore(s => s.setSseDisconnected)
  const setStep2Error  = useAppStore(s => s.setStep2Error)
  const setStep        = useAppStore(s => s.setStep)

  const missedRef = useRef(0)

  useEffect(() => {
    if (!taskId) return

    missedRef.current = 0

    const es = new EventSource(`/api/workflow/${taskId}/stream`)

    // Heartbeat watchdog: tick every 15s, trigger disconnect after 4 missed (60s)
    const heartbeatTimer = setInterval(() => {
      missedRef.current++
      if (missedRef.current >= MISSED_HEARTBEAT_THRESHOLD) {
        setDisconnect(true)
      }
    }, HEARTBEAT_INTERVAL_MS)

    es.onmessage = (e: MessageEvent) => {
      let event: SseEvent
      try {
        event = JSON.parse(e.data) as SseEvent
      } catch {
        return
      }

      // Any message resets the missed-heartbeat counter
      missedRef.current = 0
      setDisconnect(false)

      // Heartbeat: reset counter only, do NOT add to eventLog
      if (event.type === 'heartbeat') return

      appendEvent(event)

      switch (event.type) {
        case 'stage':
          addKnownStage(event.stage)
          break

        case 'knowledge_done':
          if (event.criteria) setCriteria(event.criteria)
          break

        case 'interrupt':
          setApproval(event.payload)
          break

        case 'done':
          setFinalResult(event.result ?? null, event.status)
          clearInterval(heartbeatTimer)
          es.close()
          // Both 'completed' and 'failed' advance to step 3
          setStep(3)
          break

        case 'error':
          setStep2Error(event.error)
          clearInterval(heartbeatTimer)
          es.close()
          break
      }
    }

    es.onerror = () => {
      // EventSource auto-reconnects; just surface the disconnected state in UI
      setDisconnect(true)
    }

    return () => {
      clearInterval(heartbeatTimer)
      es.close()
    }
  }, [taskId]) // eslint-disable-line react-hooks/exhaustive-deps
}
