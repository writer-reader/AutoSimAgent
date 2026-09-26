// frontend/src/components/EventLog.tsx
import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/app'
import { cn } from '@/lib/utils'
import type { SseEvent, KnowledgeSummary, ToolResult } from '@/types'

function formatTs(ts?: number) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

// ── 可折叠详情块：把任意 JSON / 代码 / 文本包成 <details>，默认折叠 ──
function Detail({ summary, children, tone = 'slate' }: {
  summary: string
  children: React.ReactNode
  tone?: 'slate' | 'blue' | 'green' | 'red' | 'amber'
}) {
  const toneCls = {
    slate: 'text-slate-500',
    blue: 'text-blue-600',
    green: 'text-emerald-600',
    red: 'text-red-600',
    amber: 'text-amber-600',
  }[tone]
  return (
    <details className="mt-1 ml-5 group">
      <summary className={cn('cursor-pointer text-xs select-none', toneCls)}>
        {summary}
        <span className="ml-1 text-slate-300 group-open:hidden">▾ 展开</span>
        <span className="ml-1 hidden group-open:inline text-slate-300">▴ 收起</span>
      </summary>
      <div className="mt-1 ml-2 border-l-2 border-slate-200 pl-3">{children}</div>
    </details>
  )
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="text-[11px] leading-snug bg-slate-100 dark:bg-zinc-900/70 rounded p-2 overflow-x-auto whitespace-pre-wrap break-words">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function KnowledgeCard({ k }: { k: KnowledgeSummary }) {
  const eqs = k.equations ?? []
  const pars = k.parameters ?? []
  const ctrls = k.controllers ?? []
  return (
    <div className="space-y-2 text-xs">
      <div className="flex gap-3 text-slate-500">
        <span>公式 {k.equation_count ?? eqs.length}</span>
        <span>参数 {k.parameter_count ?? pars.length}</span>
        <span>控制器 {k.controller_count ?? ctrls.length}</span>
      </div>
      {eqs.length > 0 && (
        <Detail summary={`公式（${eqs.length}）`} tone="blue">
          <div className="space-y-1">
            {eqs.map((e, i) => (
              <div key={i} className="flex gap-2">
                <span className="shrink-0 text-slate-400">[{e.category ?? '?'}]</span>
                <code className="text-[11px] text-slate-700 dark:text-slate-200 break-all">
                  {e.latex}
                </code>
                {e.confidence != null && (
                  <span className="ml-auto text-slate-400">{Math.round(e.confidence * 100)}%</span>
                )}
              </div>
            ))}
          </div>
        </Detail>
      )}
      {pars.length > 0 && (
        <Detail summary={`参数（${pars.length}）`} tone="blue">
          <div className="overflow-x-auto">
            <table className="text-[11px] w-full">
              <thead>
                <tr className="text-slate-400 text-left">
                  <th className="pr-3 font-normal">符号</th>
                  <th className="pr-3 font-normal">值</th>
                  <th className="pr-3 font-normal">单位</th>
                  <th className="font-normal">置信</th>
                </tr>
              </thead>
              <tbody>
                {pars.map((p, i) => (
                  <tr key={i}>
                    <td className="pr-3 font-mono">{p.symbol ?? ''}</td>
                    <td className="pr-3 font-mono">{String(p.value ?? '—')}</td>
                    <td className="pr-3">{p.unit ?? ''}</td>
                    <td>{p.confidence != null ? `${Math.round(p.confidence * 100)}%` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Detail>
      )}
      {ctrls.length > 0 && (
        <Detail summary={`控制器（${ctrls.length}）`} tone="blue">
          <ul className="space-y-0.5">
            {ctrls.map((c, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-slate-600 dark:text-slate-300">{c.type}</span>
                {c.architecture && <span className="text-slate-400">— {c.architecture}</span>}
              </li>
            ))}
          </ul>
        </Detail>
      )}
    </div>
  )
}

function ToolResultCard({ tr }: { tr: ToolResult }) {
  return (
    <div className="space-y-1 text-xs">
      <div className="flex gap-2">
        <span className={cn('font-semibold', tr.ok ? 'text-emerald-600' : 'text-red-600')}>
          {tr.ok ? '✓ 执行成功' : '✗ 执行失败'}
        </span>
        {tr.error_layer && (
          <span className="px-1.5 rounded bg-amber-100 text-amber-700 text-[10px]">{tr.error_layer}</span>
        )}
        {tr.artifacts.length > 0 && (
          <span className="text-slate-400">产物 {tr.artifacts.length}</span>
        )}
      </div>
      {tr.stderr_tail && (
        <Detail summary="stderr（尾部）" tone="red">
          <pre className="text-[11px] text-red-600 whitespace-pre-wrap break-words">{tr.stderr_tail}</pre>
        </Detail>
      )}
      {tr.stdout_tail && (
        <Detail summary="stdout（尾部）" tone="slate">
          <pre className="text-[11px] whitespace-pre-wrap break-words">{tr.stdout_tail}</pre>
        </Detail>
      )}
    </div>
  )
}

function EventRow({ event }: { event: SseEvent }) {
  if (event.type === 'heartbeat' || event.type === 'resume') return null

  const raw = event as Record<string, unknown>
  if (raw._dropped) {
    return <div className="text-xs text-yellow-600">⚠️ 部分事件已丢失</div>
  }

  if (event.type === 'node') {
    // 节点完成事件：按 node 类型展示透明化产物
    if (event.phase === 'done') {
      const node = event.node ?? ''
      return (
        <div className="pl-4 text-xs">
          <div className="flex gap-2 text-slate-400">
            <span>{formatTs(event.ts)}</span>
            <span>↳ {node} 完成</span>
          </div>
          <div className="ml-5">
            {node === 'plan' && event.plan != null && (
              <Detail summary="执行计划 plan" tone="slate">
                <JsonBlock data={event.plan} />
              </Detail>
            )}
            {node === 'generate' && event.code && (
              <Detail summary={`生成代码（${event.code.length} 字符）`} tone="slate">
                <pre className="text-[11px] text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-zinc-900/70 rounded p-2 overflow-x-auto whitespace-pre-wrap break-words">
                  {event.code.slice(0, 4000)}
                </pre>
              </Detail>
            )}
            {node === 'execute' && event.tool_result && <ToolResultCard tr={event.tool_result} />}
            {node === 'execute' && event.metrics && Object.keys(event.metrics).length > 0 && (
              <Detail summary="算出指标 results" tone="green">
                <JsonBlock data={event.metrics} />
              </Detail>
            )}
            {node === 'verify' && event.verdict && (
              <div className="mt-1 flex gap-2">
                <span className={cn('font-semibold', event.verdict.passed ? 'text-emerald-600' : 'text-red-600')}>
                  {event.verdict.passed ? '✓ 验收通过' : '✗ 验收未达标'}
                </span>
                {event.verdict.summary && <span className="text-slate-400">{event.verdict.summary}</span>}
              </div>
            )}
            {node === 'extract_knowledge' && (
              <span className="text-slate-400 text-[11px]">已重新抽取知识</span>
            )}
          </div>
        </div>
      )
    }
    // 节点开始：单行
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
        {event.knowledge && (
          <Detail summary="查看抽取的知识" tone="blue">
            <KnowledgeCard k={event.knowledge} />
          </Detail>
        )}
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

  if (event.type === 'llm_call') {
    return (
      <div className={cn(base, 'text-violet-600 dark:text-violet-400')}>
        <span className="text-slate-400 shrink-0">{formatTs(event.ts)}</span>
        <span>⚙ {event.label}</span>
      </div>
    )
  }

  if (event.type === 'llm_usage') {
    return (
      <div className="flex gap-2 pl-4 text-[11px] text-slate-400">
        <span className="shrink-0">{formatTs(event.ts)}</span>
        <span>
          ↳ {event.label} ↑{event.prompt_tokens ?? '?'} ↓{event.completion_tokens ?? '?'} tok
          {event.duration_s != null && ` · ${event.duration_s}s`}
        </span>
      </div>
    )
  }

  if (event.type === 'error') {
    // 后端主要错误：卡片化强提示（调试阶段要求所有主要报错在前端可见）
    return (
      <div className="my-1 rounded-lg border border-red-200 bg-red-50/70 dark:border-red-900 dark:bg-red-950/30 px-3 py-2">
        <div className="flex gap-2 text-sm text-red-600 dark:text-red-400 font-semibold">
          <span className="text-slate-400 shrink-0 font-normal">{formatTs(event.ts)}</span>
          <span>❌ 后端报错{event.error_class ? `（${event.error_class}）` : ''}</span>
        </div>
        <div className="ml-9 mt-0.5 text-xs text-red-600/90 dark:text-red-400/90 break-all whitespace-pre-wrap">
          {event.error}
        </div>
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

export function EventLog({ tall = false }: { tall?: boolean }) {
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
      <div className={cn(
        'min-h-[14rem] max-h-[26rem] overflow-y-auto p-4 space-y-1.5 text-sm bg-slate-50/80 dark:bg-zinc-800/50 rounded-xl',
        tall && 'xl:max-h-[calc(100vh-11rem)]',
      )}>
        {log.map(entry => (
          <EventRow key={entry.id} event={entry.event} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
