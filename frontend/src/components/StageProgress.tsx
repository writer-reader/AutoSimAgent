// frontend/src/components/StageProgress.tsx
// 阶段时间线：图标节点 + 连接线 + 顶部整体进度条。
import {
  Boxes, Brain, CircleCheck, FileText, Flag, ListChecks, Network, Play,
  UserCheck, type LucideIcon,
} from 'lucide-react'
import { useAppStore } from '@/store/app'
import { cn } from '@/lib/utils'

const STAGE_META: Record<string, { label: string; icon: LucideIcon }> = {
  'mineru':           { label: 'PDF 解析', icon: FileText },
  'adapter':          { label: '结构适配', icon: Boxes },
  'knowledge':        { label: '知识抽取', icon: Brain },
  'graph:init':       { label: '图初始化', icon: Network },
  'graph:plan':       { label: '执行规划', icon: ListChecks },
  'request_approval': { label: '等待审批', icon: UserCheck },
  'resuming':         { label: '恢复执行', icon: Play },
  'done':             { label: '完成',     icon: Flag },
}

export function StageProgress() {
  const stages       = useAppStore(s => s.knownStages)
  const currentStage = useAppStore(s => s.currentStage)
  const taskStatus   = useAppStore(s => s.taskStatus)

  const currentIdx = stages.indexOf(currentStage ?? '')
  const isFailed   = taskStatus === 'failed'
  const doneCount  = stages.filter((s, i) => i < currentIdx || (s === 'done' && taskStatus === 'completed')).length
  const pct        = Math.round((doneCount / stages.length) * 100)

  return (
    <div className="rounded-xl border border-slate-200 dark:border-zinc-700 bg-white/60 dark:bg-zinc-900/40 px-4 pt-3 pb-3.5">
      {/* 整体进度：细条 + 百分比 */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">阶段进度</span>
        <div className="flex-1 h-1 rounded-full bg-slate-200/70 dark:bg-zinc-700/60 overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-transform duration-500 ease-out origin-left',
              isFailed ? 'bg-red-400' : 'bg-blue-500',
            )}
            style={{ transform: `scaleX(${pct / 100})` }}
          />
        </div>
        <span className="text-[11px] tabular-nums text-slate-400 w-8 text-right">{pct}%</span>
      </div>

      <div className="flex items-start gap-1.5 overflow-x-auto pb-0.5">
        {stages.map((stage, idx) => {
          const meta      = STAGE_META[stage]
          const Icon      = meta?.icon ?? CircleCheck
          const isDone     = idx < currentIdx || (stage === 'done' && taskStatus === 'completed')
          const isCurrent  = idx === currentIdx && !isDone
          const isApproval = stage === 'request_approval'

          return (
            <div key={stage} className="flex items-start gap-1.5 shrink-0 min-w-0">
              {idx > 0 && (
                <div
                  className={cn(
                    'w-5 h-0.5 mt-[15px]',
                    isDone || isCurrent ? 'bg-slate-400/80' : 'bg-slate-200 dark:bg-zinc-700',
                  )}
                />
              )}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={cn(
                    'w-[30px] h-[30px] rounded-lg flex items-center justify-center border transition-all',
                    isDone && 'bg-emerald-500 border-emerald-500 text-white',
                    isCurrent && !isApproval && !isFailed && 'bg-blue-500 border-blue-500 text-white ring-4 ring-blue-500/15 animate-pulse',
                    isCurrent && isApproval  && 'bg-orange-500 border-orange-500 text-white ring-4 ring-orange-500/15 animate-pulse',
                    isCurrent && isFailed    && 'bg-red-500 border-red-500 text-white ring-4 ring-red-500/15',
                    !isDone && !isCurrent    && 'bg-background border-slate-300 text-slate-400 dark:border-zinc-600 dark:text-zinc-500',
                  )}
                >
                  <Icon className="w-3.5 h-3.5" strokeWidth={2} />
                </div>
                <span
                  className={cn(
                    'text-[11px] whitespace-nowrap leading-none',
                    isCurrent && isApproval
                      ? 'text-orange-600 dark:text-orange-400 font-semibold'
                      : isCurrent && isFailed
                        ? 'text-red-600 dark:text-red-400 font-semibold'
                        : isCurrent
                          ? 'text-blue-600 dark:text-blue-400 font-semibold'
                          : isDone
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-slate-400 dark:text-zinc-500',
                  )}
                >
                  {meta?.label ?? stage}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
