// frontend/src/steps/Step3Result.tsx
// 结果页：卡片化的验收报告。每个板块一张卡（卡片头 + 边界 + 正文），不再用裸标题漂在留白里。
// 板块顺序即叙事顺序：结论 → 证据（仿真产物 | 最终代码）→ 过程记录（折叠）。
// 逐条验收明细取最后一次 verify 结算事件（含真实 expected/actual/reason/硬编码标记）；
// 图题从最终版 MATLAB 源码的 title('...') 解析而来，回答“这张图是什么”。
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  ChevronDown, ChevronUp, CircleCheck, CircleDashed, Coins, Cpu, ExternalLink,
  FileCode2, FileText, History, Image, ListChecks, ShieldAlert,
  Timer, TriangleAlert, XCircle, type LucideIcon,
} from 'lucide-react'
import { useAppStore } from '@/store/app'
import { CodePanel } from '@/components/CodePanel'
import { EventLog } from '@/components/EventLog'
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { api } from '@/api/client'
import { extractFinalVerdict } from '@/lib/verdict'
import { cn } from '@/lib/utils'

function fmtDur(sec: number) {
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60)
  const r = Math.round(sec % 60)
  return `${m}m${r.toString().padStart(2, '0')}s`
}

const fmtInt = (n: number) => n.toLocaleString('zh-CN')

// 指标值展示：布尔/空值原样，浮点数按量级取有效数字，避免 4.394194093038095e-07 这种原始串
function fmtMetricVal(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return String(v)
    const a = Math.abs(v)
    if (a !== 0 && (a < 1e-4 || a >= 1e7)) return v.toExponential(3)
    return String(Number(v.toPrecision(6)))
  }
  return String(v)
}

// ── 从最终版 MATLAB 源码解析每个落盘图片的图题 ─────────────────────────────
// figure 块内的 title('X') 归到块内其后的 exportgraphics/saveas/print 目标文件上；
// 解析不到就返回空表，调用方退回文件名展示。只认字面量字符串，不猜测语义。
const FIG_SAVE_RE = /\b(?:exportgraphics|saveas|print)\s*\([^;]*?(['"])([^'"]+\.(?:png|jpg|jpeg|svg|pdf))\1/i
const FIG_TITLE_RE = /\b(?:sgtitle|title)\s*\(\s*(['"])([^'"]*)\1/
const FIGURE_CMD_RE = /^\s*figure\b/

function stripMatlabComment(line: string): string {
  let quote: string | null = null
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (quote) {
      if (ch === quote) quote = null
    } else if (ch === "'" || ch === '"') {
      quote = ch
    } else if (ch === '%') {
      return line.slice(0, i)
    }
  }
  return line
}

export function extractFigureTitles(code: string): Record<string, string> {
  const titles: Record<string, string> = {}
  let pending: string | null = null
  for (const raw of code.split('\n')) {
    const line = stripMatlabComment(raw)
    if (FIGURE_CMD_RE.test(line)) {
      pending = null
      continue
    }
    const t = FIG_TITLE_RE.exec(line)
    if (t) {
      pending = t[2].trim() || null
      continue
    }
    const f = FIG_SAVE_RE.exec(line)
    if (f && pending) titles[f[2].toLowerCase()] = pending
  }
  return titles
}

// ── 结果卡外壳：统一的卡片头（图标 + 标题 + 元信息 + 右侧徽标/折叠）─────────
function CardShell({
  icon: Icon, title, meta, badge, open, onToggle, bodyClassName, children,
}: {
  icon: LucideIcon
  title: string
  meta?: ReactNode
  badge?: ReactNode
  open?: boolean
  onToggle?: (v: boolean) => void
  bodyClassName?: string
  children: ReactNode
}) {
  const head = (
    <>
      <Icon className="w-4 h-4 text-slate-400 shrink-0" />
      <h2 className="text-[13px] font-semibold text-foreground">{title}</h2>
      {meta && <span className="min-w-0 truncate text-[11px] text-muted-foreground">{meta}</span>}
      <span className="ml-auto flex items-center gap-2 shrink-0">
        {badge}
        {onToggle && (open
          ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
          : <ChevronDown className="w-4 h-4 text-muted-foreground" />)}
      </span>
    </>
  )
  const body = <div className={bodyClassName ?? 'p-4'}>{children}</div>
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      {onToggle ? (
        <Collapsible open={open} onOpenChange={onToggle}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left border-b border-border bg-muted/40 hover:bg-muted/70 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-inset"
            >
              {head}
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>{body}</CollapsibleContent>
        </Collapsible>
      ) : (
        <>
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-muted/40">{head}</div>
          {body}
        </>
      )}
    </section>
  )
}

// 未达标行：指标名 + 期望/实测 + （作弊嫌疑徽标）+ 评审理由
function FailedRow({ row }: { row: import('@/types').VerdictCriterionResult }) {
  return (
    <div className="py-2.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
        <code className="text-[11.5px] font-medium px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-700 dark:text-rose-300 whitespace-nowrap">
          {row.metric || '(未命名指标)'}
        </code>
        <span className="text-xs text-muted-foreground font-mono tabular-nums">
          期望 {fmtMetricVal(row.expected)} · 实测 {fmtMetricVal(row.actual)}
        </span>
        {row.hardcoded && (
          <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-400">
            <ShieldAlert className="w-3 h-3" />
            作弊嫌疑
          </span>
        )}
      </div>
      {row.reason && (
        <p className="mt-1 pl-6 text-xs leading-relaxed text-muted-foreground">{row.reason}</p>
      )}
    </div>
  )
}

// 达标行：紧凑单行（指标 + 判定依据）；放不下时判定依据整体换行，不在指标名中间断词
function PassedRow({ row }: { row: import('@/types').VerdictCriterionResult }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1.5 min-w-0">
      <CircleCheck className="w-4 h-4 text-emerald-500 shrink-0" />
      <code className="text-[11.5px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 whitespace-nowrap">
        {row.metric || '(未命名指标)'}
      </code>
      {row.reason && (
        <span className="min-w-0 flex-1 basis-40 truncate text-right text-[11px] text-muted-foreground font-mono">{row.reason}</span>
      )}
    </div>
  )
}

const OUTCOME_STYLE = {
  pass: { icon: CircleCheck, cls: 'text-emerald-500', title: '仿真复现完成', titleCls: 'text-foreground' },
  partial: { icon: TriangleAlert, cls: 'text-amber-500', title: '验收未全部达标', titleCls: 'text-foreground' },
  fail: { icon: XCircle, cls: 'text-rose-500', title: '验收未达标', titleCls: 'text-foreground' },
  crash: { icon: XCircle, cls: 'text-destructive', title: '流水线失败', titleCls: 'text-destructive' },
} as const

export function Step3Result() {
  const result       = useAppStore(s => s.finalResult)
  const criteria     = useAppStore(s => s.criteria)
  const finalVerdict = useAppStore(s => s.finalVerdict)
  const taskId       = useAppStore(s => s.taskId)
  const taskStatus   = useAppStore(s => s.taskStatus)
  const eventLog     = useAppStore(s => s.eventLog)

  const [codeContent, setCodeContent] = useState<Record<string, string>>({})
  const [processOpen, setProcessOpen] = useState(false)
  const [codeOpen, setCodeOpen] = useState(true)

  // 过程聚合：由事件流推导（运行结束后 eventLog 仍保留在 store 中）
  const events = eventLog.map(l => l.event)
  const stageTs = events.filter(e => e.type === 'stage' && e.ts).map(e => e.ts!) 
  const doneTs  = events.find(e => e.type === 'done' && e.ts)?.ts
  const totalDur = stageTs.length && doneTs ? doneTs - stageTs[0] : null
  const usages = events.filter(e => e.type === 'llm_usage')
  const tokIn  = usages.reduce((a, u) => a + (u.prompt_tokens ?? 0), 0)
  const tokOut = usages.reduce((a, u) => a + (u.completion_tokens ?? 0), 0)
  const tokAll = usages.reduce((a, u) => a + (u.total_tokens ?? 0), 0) || tokIn + tokOut
  const rollbacks = events.filter(e =>
    e.type === 'node' && e.phase === 'done' &&
    (e as Record<string, unknown>).tool_result != null &&
    !((e as Record<string, unknown>).tool_result as { ok?: boolean }).ok,
  ).length

  // 只加载最终版代码（code_paths 的最后一个：每次执行生成 gen_N.m，N 最大即最终版）
  const finalCodePath = result?.code_paths?.length ? result.code_paths[result.code_paths.length - 1] : null
  const finalCodeName = finalCodePath ? finalCodePath.split(/[\\/]/).pop() ?? finalCodePath : null

  useEffect(() => {
    if (!taskId || !finalCodePath) return
    const filename = finalCodePath.split(/[\\/]/).pop() ?? finalCodePath
    api.codeContent(taskId, filename)
      .then(content => setCodeContent(prev => ({ ...prev, [filename]: content })))
      .catch(() => setCodeContent(prev => ({ ...prev, [filename]: '// 无法加载代码内容' })))
  }, [taskId, finalCodePath])

  function handleDownload(filename: string, content: string) {
    const blob = new Blob([content], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  // Build criteria pass/fail map keyed by criteria_id（无结算事件时的回落数据源）
  const criteriaMap = Object.fromEntries(
    (result?.verification?.criteria_results ?? []).map(r => [r.criteria_id, r])
  )
  const passedCount = criteria.filter(c => criteriaMap[c.criteria_id]?.passed === true).length

  // 逐条验收裁决：live 路径在事件流里，恢复路径在 store.finalVerdict（补拉自事件回放端点）
  const verdictRows = useMemo(() => {
    const fromLog = extractFinalVerdict(events)
    if (fromLog) return fromLog.rows
    return finalVerdict?.rows ?? null
  }, [eventLog, finalVerdict])

  const passedTotal = verdictRows ? verdictRows.filter(r => r.passed === true).length : passedCount
  const totalCount  = verdictRows ? verdictRows.length : criteria.length
  const failedRows  = verdictRows?.filter(r => r.passed !== true) ?? []
  const passedRows  = verdictRows?.filter(r => r.passed === true) ?? []
  const hardCount   = verdictRows?.filter(r => r.hardcoded === true).length ?? 0
  const hasVerdictData = (verdictRows?.length ?? 0) > 0 || criteria.length > 0
  const allPassed = hasVerdictData && totalCount > 0 && passedTotal === totalCount

  // 结论标题以验收数据为准（任务 status 只区分“没跑完就挂了”的崩溃场景）
  const outcome: keyof typeof OUTCOME_STYLE = (() => {
    if (!result) return 'crash'
    if (totalCount > 0) {
      if (passedTotal === totalCount) return 'pass'
      return passedTotal > 0 ? 'partial' : 'fail'
    }
    return taskStatus === 'completed' ? 'pass' : 'fail'
  })()
  const outcomeStyle = OUTCOME_STYLE[outcome]
  const OutcomeIcon = outcomeStyle.icon

  const figures = result?.artifacts?.filter(a => a.kind === 'figure') ?? []
  const otherArts = result?.artifacts?.filter(a => a.kind !== 'figure') ?? []

  // 图题：解析最终版代码里的 title('...') → fig_N.png
  const finalCodeBody = finalCodeName ? codeContent[finalCodeName] : undefined
  const figureTitles = useMemo(
    () => (finalCodeBody ? extractFigureTitles(finalCodeBody) : {}),
    [finalCodeBody],
  )
  const codeLines = finalCodeBody ? finalCodeBody.split('\n').length : null

  const showVerdictCard = hasVerdictData && result
  const showFiguresCard = Boolean(result) && (figures.length > 0 || otherArts.length > 0)
  const showCodeCard = Boolean(result && finalCodeName)
  const figuresMeta = figures.length > 0
    ? `共 ${figures.length} 张${finalCodeName ? ` · 输出自 ${finalCodeName}` : ''}`
    : '登记的运行产物'
  const codeMeta = finalCodeName
    ? `${finalCodeName}${(result?.code_paths.length ?? 0) > 1 ? ` · 共迭代 ${result!.code_paths.length} 版` : ''}${codeLines != null ? ` · ${codeLines} 行` : ''}`
    : null

  return (
    <div className="space-y-6">
      {/* 标题 + 系统判定一句话 */}
      <div>
        <div className="flex items-center gap-2.5">
          <OutcomeIcon className={cn('w-6 h-6 shrink-0', outcomeStyle.cls)} />
          <h1 className={cn(
            'text-2xl font-semibold tracking-tight [text-wrap:balance]',
            outcomeStyle.titleCls,
          )}>
            {outcomeStyle.title}
          </h1>
        </div>
        {result?.verdict && (
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed max-w-[62ch]">{result.verdict}</p>
        )}
      </div>

      {/* 运行总结卡：把运行时的过程数据收拢成一行数字，衔接 Step2 的监控视图 */}
      <section className="grid grid-cols-2 sm:grid-cols-4 gap-px rounded-xl border border-border bg-border overflow-hidden">
        {[
          { icon: Timer, cls: 'text-blue-500',        label: '总耗时',   value: totalDur != null ? fmtDur(totalDur) : '—' },
          { icon: Cpu,    cls: 'text-violet-500',     label: 'LLM 调用', value: usages.length ? `${usages.length} 次` : (result ? `${result.tool_calls} 次工具` : '—') },
          { icon: Coins,  cls: 'text-amber-500',      label: 'Token',    value: tokAll ? fmtInt(tokAll) : '—', sub: tokAll ? `↑${fmtInt(tokIn)} ↓${fmtInt(tokOut)}` : undefined },
          { icon: TriangleAlert, cls: rollbacks > 0 ? 'text-rose-500' : 'text-slate-400', label: '执行受阻', value: result ? `${rollbacks} 次` : '—', sub: result ? `共 ${result.tool_calls} 次工具调用` : undefined },
        ].map(stat => (
          <div key={stat.label} className="bg-card px-4 py-3">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/70">
              <stat.icon className={cn('w-3.5 h-3.5', stat.cls)} />
              {stat.label}
            </div>
            <div className="mt-1 text-lg font-semibold tabular-nums tracking-tight text-foreground">
              {stat.value}
              {stat.sub && <span className="ml-1.5 text-[10px] font-normal text-muted-foreground/70 tabular-nums">{stat.sub}</span>}
            </div>
          </div>
        ))}
      </section>

      {/* 验收结论卡：得分头图 + 未达标明细（作弊嫌疑亮牌）+ 达标清单 */}
      {showVerdictCard && (
        <CardShell
          icon={ListChecks}
          title="验收结论"
          meta={verdictRows ? '逐条裁决 · 来自最后一次 verify 结算' : '验收标准逐条核对'}
          badge={totalCount > 0 && (
            <span className={cn(
              'text-[11px] px-2 py-0.5 rounded-full font-medium tabular-nums',
              allPassed
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400'
                : 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-400',
            )}>
              {passedTotal}/{totalCount} 达标
            </span>
          )}
        >
          {totalCount > 0 ? (
            <>
              {/* 得分头图 */}
              <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
                <div className="flex items-baseline gap-1.5">
                  <span className="text-4xl font-semibold tabular-nums tracking-tight text-foreground">{passedTotal}</span>
                  <span className="text-lg text-muted-foreground tabular-nums">/ {totalCount}</span>
                  <span className="ml-1.5 text-sm text-muted-foreground">项达标</span>
                </div>
                <div className="flex-1 min-w-[220px] max-w-md space-y-1.5">
                  <div className="flex h-2 overflow-hidden rounded-full bg-rose-400/60 dark:bg-rose-500/30" role="img" aria-label={`达标 ${passedTotal} 项，未达标 ${totalCount - passedTotal} 项`}>
                    <div
                      className="h-full rounded-full bg-emerald-500"
                      style={{ width: `${totalCount ? (passedTotal / totalCount) * 100 : 0}%` }}
                    />
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground tabular-nums">
                    <span className="text-emerald-600 dark:text-emerald-400">达标 {passedTotal}</span>
                    <span className="text-rose-600 dark:text-rose-400">未达标 {totalCount - passedTotal}</span>
                    {hardCount > 0 && (
                      <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                        <ShieldAlert className="w-3 h-3" />
                        作弊嫌疑 {hardCount}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {verdictRows ? (
                <>
                  {/* 未达标明细 */}
                  {failedRows.length > 0 && (
                    <div className="mt-6">
                      <h3 className="text-xs font-medium text-rose-600 dark:text-rose-400">
                        未达标 · {failedRows.length} 项
                      </h3>
                      <div className="mt-1 divide-y divide-border/70">
                        {failedRows.map((r, i) => (
                          <FailedRow key={(r.metric ?? 'row') + i} row={r} />
                        ))}
                      </div>
                    </div>
                  )}
                  {/* 达标清单 */}
                  {passedRows.length > 0 && (
                    <div className="mt-5">
                      <h3 className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
                        达标 · {passedRows.length} 项
                      </h3>
                      <div className="mt-1 divide-y divide-border/50">
                        {passedRows.map((r, i) => (
                          <PassedRow key={(r.metric ?? 'row') + i} row={r} />
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                /* 回落：无结算事件时按验收标准列表展示 */
                <div className="mt-5 space-y-1.5">
                  {criteria.map(c => {
                    const res = criteriaMap[c.criteria_id]
                    const passed = res?.passed
                    return (
                      <div key={c.criteria_id} className={cn(
                        'pl-3 border-l-2 text-sm py-1 flex items-baseline gap-2',
                        res === undefined && 'border-border',
                        passed === true  && 'border-emerald-400/70',
                        passed === false && 'border-rose-400/60',
                      )}>
                        <span className="shrink-0 flex items-center pt-0.5">
                          {passed === true ? (
                            <CircleCheck className="w-3.5 h-3.5 text-emerald-500" />
                          ) : passed === false ? (
                            <XCircle className="w-3.5 h-3.5 text-rose-400" />
                          ) : (
                            <CircleDashed className="w-3.5 h-3.5 text-slate-300 dark:text-slate-600" />
                          )}
                        </span>
                        <span className={cn(
                          'leading-relaxed',
                          res === undefined && 'text-muted-foreground',
                          passed === false && 'text-muted-foreground',
                          passed === true && 'text-foreground',
                        )}>
                          {c.description}
                          {res?.detail && (
                            <span className="text-muted-foreground/60 ml-1.5 text-xs">{res.detail}</span>
                          )}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">本次运行没有产出可核对的验收数据。</p>
          )}
        </CardShell>
      )}

      {/* 证据区：仿真产物 | 最终代码 + 过程记录 */}
      {(showFiguresCard || showCodeCard) && (
        <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
          {/* 左列：仿真产物 */}
          <div className="min-w-0 space-y-6">
            {showFiguresCard && (
              <CardShell
                icon={Image}
                title="仿真产物"
                meta={figuresMeta}
              >
                {figures.length > 0 && (
                  <div className="space-y-4">
                    {figures.map((a, i) => {
                      const filename = a.path.split(/[\\/]/).pop() ?? a.path
                      const stem = filename.replace(/\.[^.]+$/, '')
                      const hasRealTitle = Boolean(a.label) && a.label !== stem && a.label !== filename
                      const figTitle = figureTitles[filename.toLowerCase()]
                        ?? (hasRealTitle ? a.label : null)
                      const url = api.artifactUrl(taskId ?? '', filename)
                      return (
                        <figure
                          key={a.path}
                          className="overflow-hidden rounded-lg border border-border bg-slate-50/60 dark:bg-zinc-900/40"
                        >
                          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
                            <span className="shrink-0 rounded bg-violet-100 px-1.5 py-0.5 font-mono text-[10px] font-medium text-violet-700 dark:bg-violet-950/60 dark:text-violet-300">
                              图 {i + 1}
                            </span>
                            <span className="min-w-0 truncate text-[13px] font-medium text-foreground" title={figTitle ?? filename}>
                              {figTitle ?? filename}
                            </span>
                            {figTitle && (
                              <span className="ml-auto shrink-0 font-mono text-[10.5px] text-muted-foreground">{filename}</span>
                            )}
                            <a
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                              className={cn(
                                'inline-flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground',
                                !figTitle && 'ml-auto',
                              )}
                            >
                              <ExternalLink className="w-3 h-3" />
                              原图
                            </a>
                          </div>
                          <a href={url} target="_blank" rel="noreferrer" className="block">
                            <img
                              src={url}
                              alt={figTitle ?? filename}
                              className="w-full h-auto"
                              loading="lazy"
                            />
                          </a>
                          <figcaption className="flex items-center gap-1.5 border-t border-border px-3 py-1.5 text-[11px] text-muted-foreground">
                            <FileText className="w-3 h-3 shrink-0 text-slate-400" />
                            {figTitle ? `MATLAB 仿真输出 · 由最终版 ${finalCodeName ?? ''} 绘制` : 'MATLAB 仿真输出'}
                          </figcaption>
                        </figure>
                      )
                    })}
                  </div>
                )}
                {otherArts.length > 0 && (
                  <div className={cn('flex flex-wrap gap-1.5', figures.length > 0 && 'mt-4')}>
                    {otherArts.map(a => {
                      const filename = a.path.split(/[\\/]/).pop() ?? a.path
                      return (
                        <span key={a.path} className="text-[11px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-zinc-800 text-muted-foreground inline-flex items-center gap-1">
                          <FileText className="w-3 h-3 text-slate-400" />
                          [{a.kind}] {filename}
                        </span>
                      )
                    })}
                  </div>
                )}
              </CardShell>
            )}
          </div>

          {/* 右列：最终代码 + 过程记录 */}
          <div className="min-w-0 space-y-6">
            {showCodeCard && (
              <CardShell
                icon={FileCode2}
                title="最终代码"
                meta={codeMeta}
                open={codeOpen}
                onToggle={setCodeOpen}
                bodyClassName="p-3"
              >
                {codeContent[finalCodeName!] !== undefined ? (
                  <CodePanel
                    language="matlab"
                    value={codeContent[finalCodeName!]}
                    readOnly
                    onDownload={() => handleDownload(finalCodeName!, codeContent[finalCodeName!])}
                  />
                ) : (
                  <div className="text-sm text-muted-foreground py-6 text-center">加载中…</div>
                )}
              </CardShell>
            )}

            {eventLog.length > 0 && (
              <CardShell
                icon={History}
                title="过程记录"
                meta={`${eventLog.length} 条事件 · 运行时的完整留痕`}
                open={processOpen}
                onToggle={setProcessOpen}
                bodyClassName="p-3"
              >
                <EventLog />
              </CardShell>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
