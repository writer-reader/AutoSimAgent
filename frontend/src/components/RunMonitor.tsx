// frontend/src/components/RunMonitor.tsx
// 运行监控面板：统计瓦片 + 阶段耗时 / LLM 调用时间线 / 错误汇总。
// 数据全部由 SSE 事件流在前端推导，不发额外请求；调试阶段要求后端主要报错在此汇总可见。
import { useEffect, useState } from 'react'
import { CircleCheck, Coins, Cpu, Route, TriangleAlert, Zap, type LucideIcon } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { cn } from '@/lib/utils'
import type { SseEvent } from '@/types'

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [active])
  return now
}

function fmtDur(sec: number) {
  if (sec < 60) return `${Math.max(0, Math.round(sec))}s`
  const m = Math.floor(sec / 60)
  const r = Math.round(sec % 60)
  return `${m}m${r.toString().padStart(2, '0')}s`
}

function fmtTs(ts?: number) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

// 里程碑事件：阶段切换 / 终态，用于切分阶段耗时
function isMilestone(e: SseEvent) {
  return e.type === 'stage' || e.type === 'done' || e.type === 'error'
}

export function RunMonitor() {
  const log = useAppStore(s => s.eventLog)
  const events = log.map(l => l.event)

  const hasTerminal = events.some(e => e.type === 'done' || e.type === 'error')
  const nowSec = useNow(!hasTerminal) / 1000

  // ── 阶段耗时：相邻里程碑事件的时间差；最后一段若未结束则实时计时 ──
  const stageRows: { label: string; startTs?: number; dur: number | null }[] = []
  for (let i = 0; i < events.length; i++) {
    const e = events[i]
    if (!isMilestone(e)) continue
    const label = e.type === 'stage' ? (e.label ?? e.stage) : e.type === 'done' ? '流水线结束' : '异常结束'
    // 找下一个里程碑事件的时间戳
    let nextTs: number | null = null
    for (let j = i + 1; j < events.length; j++) {
      if (isMilestone(events[j]) && events[j].ts) { nextTs = events[j].ts!; break }
    }
    const dur = nextTs != null && e.ts
      ? nextTs - e.ts
      : null // 仍在进行中
    stageRows.push({ label, startTs: e.ts, dur })
  }
  // 只显示最近 4 个阶段，最早的折叠
  const shownStages = stageRows.slice(-4)
  const hiddenStageCount = stageRows.length - shownStages.length

  // ── LLM 调用时间线 ──
  const llmCalls = events.filter(e => e.type === 'llm_call')
  const lastLogTs = events.length ? events[events.length - 1].ts : undefined
  const runningCall = llmCalls.length && llmCalls[llmCalls.length - 1].ts === lastLogTs
    ? llmCalls[llmCalls.length - 1]
    : null

  // ── Token 用量：llm_usage 事件汇总 ──
  const usages = events.filter(e => e.type === 'llm_usage')
  const sumTok = (pick: (u: typeof usages[number]) => number | null | undefined) =>
    usages.reduce((acc, u) => acc + (pick(u) ?? 0), 0)
  const totIn  = sumTok(u => u.prompt_tokens)
  const totOut = sumTok(u => u.completion_tokens)
  const totAll = sumTok(u => u.total_tokens) || totIn + totOut
  const fmtInt = (n: number) => n.toLocaleString('zh-CN')

  // ── 错误汇总：error 事件 + 工具执行失败 ──
  const errors = events.filter(e => e.type === 'error')
  const toolFails = events.filter(e =>
    e.type === 'node' && e.phase === 'done' &&
    (e as Record<string, unknown>).tool_result != null &&
    !((e as Record<string, unknown>).tool_result as { ok?: boolean }).ok,
  )
  const errorCount = errors.length + toolFails.length

  const SectionTitle = ({ text, icon: Icon, badge, tone = 'slate' }: {
    text: string; icon: LucideIcon; badge?: string; tone?: 'slate' | 'red'
  }) => (
    <div className="flex items-center gap-1.5">
      <Icon className={cn('w-3.5 h-3.5', tone === 'red' && errorCount > 0 ? 'text-red-500' : 'text-slate-400')} />
      <span className="text-xs font-semibold text-slate-500">{text}</span>
      {badge != null && (
        <span className={cn(
          'text-[10px] px-1.5 rounded tabular-nums',
          badge === '0' ? 'bg-slate-100 text-slate-400 dark:bg-zinc-800' : tone === 'red' ? 'bg-red-100 text-red-600 dark:bg-red-950/60' : 'bg-slate-100 text-slate-500 dark:bg-zinc-800',
        )}>
          {badge}
        </span>
      )}
    </div>
  )

  // 顶部统计瓦片
  const tiles: { icon: LucideIcon; label: string; value: string; sub?: string; cls: string }[] = [
    {
      icon: Route, label: '阶段', value: stageRows.length ? String(stageRows.length) : '—',
      sub: stageRows.length ? (stageRows[stageRows.length - 1].dur == null ? '进行中' : '已结算') : undefined,
      cls: 'text-blue-600 dark:text-blue-400',
    },
    {
      icon: Cpu, label: 'LLM 调用', value: llmCalls.length ? `${llmCalls.length} 次` : '—',
      sub: runningCall ? '1 次进行中' : undefined,
      cls: 'text-violet-600 dark:text-violet-400',
    },
    {
      icon: Coins, label: 'Token', value: usages.length ? fmtInt(totAll) : '—',
      sub: usages.length ? `${usages.length} 次用量` : undefined,
      cls: 'text-amber-600 dark:text-amber-400',
    },
    {
      icon: errorCount > 0 ? TriangleAlert : CircleCheck, label: '错误', value: String(errorCount),
      cls: errorCount > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400',
    },
  ]

  return (
    <div className="rounded-xl border border-slate-200 dark:border-zinc-700 bg-white/60 dark:bg-zinc-900/40 px-4 py-3 space-y-3">
      <div className="text-sm font-medium text-foreground">运行监控</div>

      {/* 统计瓦片 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {tiles.map(t => (
          <div key={t.label} className="rounded-lg border border-slate-200/80 dark:border-zinc-700/60 bg-slate-50/60 dark:bg-zinc-800/30 px-2.5 py-2">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-400">
              <t.icon className={cn('w-3.5 h-3.5', t.cls)} />
              {t.label}
            </div>
            <div className="mt-1 text-base font-semibold tabular-nums tracking-tight text-foreground leading-none">
              {t.value}
              {t.sub && <span className="ml-1 text-[10px] font-normal text-muted-foreground/70">{t.sub}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* 阶段耗时 */}
      <div className="space-y-1">
        <SectionTitle text="阶段耗时" icon={Route} />
        {shownStages.length === 0 && (
          <div className="text-xs text-slate-400 flex items-center gap-1.5"><Zap className="w-3 h-3" /> 等待事件…</div>
        )}
        {shownStages.map((row, i) => {
          const isRunning = row.dur == null
          return (
            <div key={i} className="flex gap-2 text-xs items-baseline">
              <span className="text-slate-400 shrink-0 w-14">{fmtTs(row.startTs)}</span>
              <span className="text-slate-600 dark:text-slate-300">{row.label}</span>
              <span className={isRunning ? 'ml-auto text-blue-600 font-medium' : 'ml-auto text-slate-400'}>
                {isRunning && row.startTs ? `${fmtDur(nowSec - row.startTs)} …` : row.dur != null ? fmtDur(row.dur) : ''}
              </span>
            </div>
          )
        })}
        {hiddenStageCount > 0 && (
          <div className="text-[11px] text-slate-400">（前面还有 {hiddenStageCount} 个阶段）</div>
        )}
      </div>

      {/* LLM 调用 */}
      <div className="space-y-1">
        <SectionTitle text="LLM 调用" icon={Cpu} badge={String(llmCalls.length)} />
        {llmCalls.length === 0 && <div className="text-xs text-slate-400">暂无调用</div>}
        {llmCalls.slice(-3).map((e, i) => {
          const isRunning = runningCall != null && i === llmCalls.slice(-3).length - 1
          return (
            <div key={log.length - llmCalls.slice(-3).length + i} className="flex gap-2 text-xs items-baseline">
              <span className="text-slate-400 shrink-0 w-14">{fmtTs(e.ts)}</span>
              <span className="text-violet-600 dark:text-violet-400 flex items-center gap-1 min-w-0">
                <Zap className="w-3 h-3 shrink-0" />
                <span className="truncate">{e.label}</span>
              </span>
              {isRunning && e.ts && (
                <span className="ml-auto text-blue-600 font-medium">{fmtDur(nowSec - e.ts)} …</span>
              )}
            </div>
          )
        })}
        {llmCalls.length > 3 && <div className="text-[11px] text-slate-400">（仅显示最近 3 次）</div>}
      </div>

      {/* Token 用量 */}
      <div className="space-y-1">
        <SectionTitle text="Token 用量" icon={Coins} badge={usages.length > 0 ? `${usages.length} 次调用` : '0'} />
        {usages.length === 0 && <div className="text-xs text-slate-400">暂无调用</div>}
        {usages.length > 0 && (
          <div className="text-xs text-slate-600 dark:text-slate-300">
            合计 <span className="font-semibold">{fmtInt(totAll)}</span> tok
            <span className="text-slate-400">（↑输入 {fmtInt(totIn)} / ↓输出 {fmtInt(totOut)}）</span>
          </div>
        )}
        {usages.slice(-3).map((u, i) => (
          <div key={`u${i}`} className="flex gap-2 text-xs items-baseline">
            <span className="text-slate-400 shrink-0 w-14">{fmtTs(u.ts)}</span>
            <span className="text-slate-600 dark:text-slate-300 truncate">{u.label}</span>
            <span className="ml-auto shrink-0 text-slate-400">
              ↑{fmtInt(u.prompt_tokens ?? 0)} ↓{fmtInt(u.completion_tokens ?? 0)}
              {u.duration_s != null && ` · ${u.duration_s}s`}
            </span>
          </div>
        ))}
        {usages.length > 3 && <div className="text-[11px] text-slate-400">（仅显示最近 3 次）</div>}
      </div>

      {/* 错误汇总 */}
      <div className="space-y-1">
        <SectionTitle text="错误" icon={TriangleAlert} badge={String(errorCount)} tone="red" />
        {errorCount === 0 && (
          <div className="text-xs text-slate-400 flex items-center gap-1.5">
            <CircleCheck className="w-3 h-3 text-emerald-500" /> 暂无错误
          </div>
        )}
        {errors.slice(-3).map((e, i) => (
          <div key={`e${i}`} className="flex gap-2 text-xs items-baseline">
            <span className="text-slate-400 shrink-0 w-14">{fmtTs(e.ts)}</span>
            <span className="text-red-600 dark:text-red-400 break-all">
              {e.error_class ? `（${e.error_class}）` : ''}{e.error}
            </span>
          </div>
        ))}
        {toolFails.slice(-2).map((e, i) => (
          <div key={`t${i}`} className="flex gap-2 text-xs items-baseline">
            <span className="text-slate-400 shrink-0 w-14">{fmtTs(e.ts)}</span>
            <span className="text-red-600 dark:text-red-400">MATLAB 执行失败（详见事件日志）</span>
          </div>
        ))}
      </div>
    </div>
  )
}
