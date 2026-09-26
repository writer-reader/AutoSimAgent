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
  const clearStep2Error = useAppStore(s => s.clearStep2Error)
  const setTaskStatus  = useAppStore(s => s.setTaskStatus)
  const setStep        = useAppStore(s => s.setStep)
  const setLastSeq     = useAppStore(s => s.setLastSeq)
  // streamNonce 变化时强制重建 EventSource（失败/中断任务点「继续」后恢复事件流）
  const streamNonce    = useAppStore(s => s.streamNonce)

  const missedRef = useRef(0)

  useEffect(() => {
    if (!taskId) return

    missedRef.current = 0

    // 带上已收到的最大 seq：恢复连接时不重放历史事件（lastSeq=0 时全量，天然覆盖刷新页面场景）
    const afterSeq = useAppStore.getState().lastSeq
    const url = `/api/workflow/${taskId}/stream${afterSeq > 0 ? `?after_seq=${afterSeq}` : ''}`
    const es = new EventSource(url)

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

      // 记录 SSE 全局 seq（SSE 帧的 id 字段），供断线/手动重连时从断点续传
      const seq = Number(e.lastEventId)
      if (seq > 0) setLastSeq(seq)

      // Heartbeat: reset counter only, do NOT add to eventLog
      if (event.type === 'heartbeat') return

      appendEvent(event)

      switch (event.type) {
        case 'stage':
          addKnownStage(event.stage)
          // 回放/续传中看到新阶段 = 任务仍在推进：清掉旧失败标记（restart 前的 error 属于历史）
          clearStep2Error()
          setTaskStatus('running')
          break

        case 'knowledge_done':
          if (event.criteria) setCriteria(event.criteria)
          clearStep2Error()
          break

        case 'llm_call':
          clearStep2Error()
          break

        case 'restart':
        case 'resume':
          clearStep2Error()
          setTaskStatus('running')
          break

        case 'interrupt':
          setApproval(event.payload)
          setTaskStatus('awaiting_approval')
          break

        case 'done':
          // 后端终态收尾哨兵没有 status 字段，不算真正完成（只代表本流结束）
          if (!event.status) {
            clearInterval(heartbeatTimer)
            es.close()
            break
          }
          setFinalResult(event.result ?? null, event.status)
          clearInterval(heartbeatTimer)
          es.close()
          // Both 'completed' and 'failed' advance to step 3
          setStep(3)
          break

        case 'error':
          // 只标记失败、不主动关流：后端发完 error 会收流，EventSource 自动重连；
          // 若任务随后被 restart/resume，重连收到的新事件会把失败标记清掉
          setStep2Error(event.error)
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
  }, [taskId, streamNonce]) // eslint-disable-line react-hooks/exhaustive-deps
}
