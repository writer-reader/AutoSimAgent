// frontend/src/components/EventLog.tsx
import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/app'
import { cn } from '@/lib/utils'
import type { SseEvent } from '@/types'

function formatTs(ts?: number) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

function EventRow({ event }: { event: SseEvent }) {
  if (event.type === 'heartbeat' || event.type === 'resume') return null

  // Check _dropped BEFORE type-specific branches
  const raw = event as Record<string, unknown>
  if (raw._dropped) {
    return (
      <div className="text-xs text-yellow-600">⚠️ 部分事件已丢失</div>
    )
  }

  if (event.type === 'node') {
    return (
      <div className="flex gap-2 pl-4 text-xs text-slate-400">
        <span>{formatTs(event.ts)}</span>
        <span>↳ {event.stage}</span>
      </div>
    )
  }

  const base = 'flex gap-2 text-sm'

  if (event.type === 'stage') {
    return (
      <div className={cn(base, 'text-slate-600')}>
        <span className="text-slate-400 shrink-0">{formatTs(event.ts)}</span>
        <span>{event.label}</span>
      </div>
    )
  }

  if (event.type === 'knowledge_done') {
    return (
      <div className={cn(base, 'text-blue-600')}>
        <span className="text-slate-400 shrink-0">{formatTs(event.ts)}</span>
        <span>知识抽取完成，{event.criteria_count} 条验收标准</span>
      </div>
    )
  }

  if (event.type === 'interrupt') {
    return (
      <div className={cn(base, 'text-orange-600 font-semibold')}>
        <span className="text-slate-400 shrink-0">{formatTs(event.ts)}</span>
        <span>⚠️ 等待人工审批：{event.payload.tool}</span>
      </div>
    )
  }

  if (event.type === 'error') {
    return (
      <div className={cn(base, 'text-red-600')}>
        <span className="text-slate-400 shrink-0">{formatTs(event.ts)}</span>
        <span>❌ {event.error}</span>
      </div>
    )
  }

  if (event.type === 'done') {
    return (
      <div className={cn(base, 'text-slate-600')}>
        <span className="text-slate-400 shrink-0">{formatTs(event.ts)}</span>
        <span>✅ 流水线完成 ({event.status})</span>
      </div>
    )
  }

  return null
}

export function EventLog() {
  const log          = useAppStore(s => s.eventLog)
  const disconnected = useAppStore(s => s.sseDisconnected)
  const bottomRef    = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  return (
    <div className="relative">
      {disconnected && (
        <div className="sticky top-0 z-10 bg-yellow-50 border-b border-yellow-200 px-3 py-1 text-xs text-yellow-700">
          连接已中断，正在重连…
        </div>
      )}
      <div className="min-h-[14rem] max-h-[26rem] overflow-y-auto p-4 space-y-1.5 text-sm bg-slate-50/80 dark:bg-zinc-800/50 rounded-xl">
        {log.map(entry => (
          <EventRow key={entry.id} event={entry.event} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
