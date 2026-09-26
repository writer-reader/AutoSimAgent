// frontend/src/steps/Step3Result.tsx
// 结果页：结论优先的叙事顺序 —— 运行总结卡 → 验收结论 → 仿真产物 → 最终代码 → 过程记录（折叠）。
// 过程数据（耗时/Token/回滚）全部由事件流聚合而来，衔接运行时的监控视图（OpenHands 式 run summary）。
// xl+ 双栏：左（验收 + 产物）/ 右（代码 + 过程记录），以下回落单栏。
import { useEffect, useState } from 'react'
import {
  CircleCheck, CircleDashed, Coins, Cpu, FileCode2, FilePlus2, FileText,
  Image, ListChecks, Timer, TriangleAlert, XCircle, type LucideIcon,
} from 'lucide-react'
import { useAppStore } from '@/store/app'
import { CodePanel } from '@/components/CodePanel'
import { EventLog } from '@/components/EventLog'
import { Button } from '@/components/ui/button'
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { api } from '@/api/client'
import { cn } from '@/lib/utils'

function fmtDur(sec: number) {
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60)
  const r = Math.round(sec % 60)
  return `${m}m${r.toString().padStart(2, '0')}s`
}

const fmtInt = (n: number) => n.toLocaleString('zh-CN')

// 节标题：上方留白大于下方（分节留白归节与节之间，不归标题与正文）
function SectionTitle({ text, hint, icon: Icon }: { text: string; hint?: string; icon?: LucideIcon }) {
  return (
    <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
      {Icon && <Icon className="w-3.5 h-3.5 text-slate-400" />}
      {text}
      {hint && <span className="normal-case tracking-normal text-slate-400/70 font-normal">{hint}</span>}
    </h2>
  )
}

export function Step3Result() {
  const result       = useAppStore(s => s.finalResult)
  const criteria     = useAppStore(s => s.criteria)
  const taskId       = useAppStore(s => s.taskId)
  const status       = useAppStore(s => s.taskStatus)
  const eventLog     = useAppStore(s => s.eventLog)
  const startNewTask = useAppStore(s => s.startNewTask)

  const [codeContent, setCodeContent] = useState<Record<string, string>>({})
  const [processOpen, setProcessOpen] = useState(false)
  const [codeOpen, setCodeOpen] = useState(true)

  const isSuccess = status === 'completed'

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

  // Build criteria pass/fail map keyed by criteria_id
  const criteriaMap = Object.fromEntries(
    (result?.verification?.criteria_results ?? []).map(r => [r.criteria_id, r])
  )
  const passedCount = criteria.filter(c => criteriaMap[c.criteria_id]?.passed === true).length

  const figures = result?.artifacts?.filter(a => a.kind === 'figure') ?? []
  const otherArts = result?.artifacts?.filter(a => a.kind !== 'figure') ?? []

  return (
    <div className="space-y-8">
      {/* 标题 + 结论 */}
      <div>
        <div className="flex items-center gap-2.5">
          {isSuccess
            ? <CircleCheck className="w-6 h-6 text-emerald-500 shrink-0" />
            : <XCircle className="w-6 h-6 text-destructive shrink-0" />}
          <h1 className={cn(
            'text-2xl font-semibold tracking-tight [text-wrap:balance]',
            isSuccess ? 'text-foreground' : 'text-destructive',
          )}>
            {isSuccess ? '仿真复现完成' : '流水线失败'}
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
          <div key={stat.label} className="bg-background px-4 py-3">
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

      {/* xl+ 双栏：左（验收 + 产物）/ 右（代码 + 过程记录） */}
      <div className="grid gap-x-8 gap-y-8 xl:grid-cols-2 xl:items-start">

        {/* 左列 */}
        <div className="space-y-8 min-w-0">
          {/* 验收结论 */}
          {criteria.length > 0 && (
            <section className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <SectionTitle text="验收结论" icon={ListChecks} />
                <span className={cn(
                  'text-[11px] px-2 py-0.5 rounded-full font-medium tabular-nums',
                  passedCount === criteria.length
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400'
                    : 'bg-slate-100 text-slate-500 dark:bg-zinc-800 dark:text-zinc-400',
                )}>
                  {passedCount === criteria.length ? '全部达标' : `${passedCount}/${criteria.length} 达标`}
                </span>
              </div>
              <div className="space-y-1.5">
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
            </section>
          )}

          {/* 仿真产物 */}
          {figures.length > 0 && (
            <section className="space-y-3">
              <SectionTitle text="仿真产物" icon={Image} hint={`${figures.length} 张图`} />
              <div className="grid grid-cols-1 gap-3">
                {figures.map(a => {
                  const filename = a.path.split(/[\\/]/).pop() ?? a.path
                  return (
                    <a
                      key={a.path}
                      href={api.artifactUrl(taskId ?? '', filename)}
                      target="_blank"
                      rel="noreferrer"
                      className="block rounded-xl border border-border overflow-hidden bg-slate-50/60 dark:bg-zinc-900/40 hover:border-slate-400 dark:hover:border-zinc-500 transition-colors"
                    >
                      <img
                        src={api.artifactUrl(taskId ?? '', filename)}
                        alt={a.label || filename}
                        className="w-full h-auto"
                      />
                      <div className="px-3 py-1.5 text-xs text-muted-foreground truncate flex items-center gap-1.5">
                        <Image className="w-3 h-3 shrink-0 text-slate-400" />
                        {a.label || filename}
                      </div>
                    </a>
                  )
                })}
              </div>
              {otherArts.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
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
            </section>
          )}
        </div>

        {/* 右列 */}
        <div className="space-y-8 min-w-0">
          {/* 最终版代码（只展示最后一次生成的版本） */}
          {finalCodeName && (
            <section className="space-y-3">
              <Collapsible open={codeOpen} onOpenChange={setCodeOpen}>
                <CollapsibleTrigger asChild>
                  <button className="w-full text-left focus-visible:ring-2 focus-visible:ring-blue-500 rounded">
                    <SectionTitle text="最终代码" icon={FileCode2} hint={codeOpen ? `▲ ${finalCodeName}` : `▼ ${finalCodeName}`} />
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-2">
                    {codeContent[finalCodeName] !== undefined ? (
                      <CodePanel
                        language="matlab"
                        value={codeContent[finalCodeName]}
                        readOnly
                        onDownload={() => handleDownload(finalCodeName, codeContent[finalCodeName])}
                      />
                    ) : (
                      <div className="text-sm text-muted-foreground py-6 text-center">加载中…</div>
                    )}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </section>
          )}

          {/* 过程记录（默认折叠：运行时的完整事件流在此归档） */}
          {eventLog.length > 0 && (
            <section className="space-y-3">
              <Collapsible open={processOpen} onOpenChange={setProcessOpen}>
                <CollapsibleTrigger asChild>
                  <button className="text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 rounded">
                    {processOpen ? '收起' : '展开'}完整过程记录（{eventLog.length} 条事件）
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-2">
                    <EventLog />
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </section>
          )}
        </div>
      </div>

      <div className="flex justify-end border-t border-border pt-5">
        <Button variant="outline" size="sm" className="gap-1.5" onClick={startNewTask}>
          <FilePlus2 className="w-4 h-4" />
          新建任务，复现另一篇
        </Button>
      </div>
    </div>
  )
}
