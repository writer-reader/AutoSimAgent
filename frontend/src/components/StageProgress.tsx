// frontend/src/components/StageProgress.tsx
import { useAppStore } from '@/store/app'
import { cn } from '@/lib/utils'

const STAGE_LABELS: Record<string, string> = {
  'mineru':           'PDF 解析',
  'adapter':          '结构适配',
  'knowledge':        '知识抽取',
  'graph:init':       '图初始化',
  'graph:plan':       '执行规划',
  'request_approval': '等待审批',
  'resuming':         '恢复执行',
  'done':             '完成',
}

export function StageProgress() {
  const stages       = useAppStore(s => s.knownStages)
  const currentStage = useAppStore(s => s.currentStage)

  const currentIdx = stages.indexOf(currentStage ?? '')

  return (
    <div className="flex items-center gap-2 overflow-x-auto py-2 px-4">
      {stages.map((stage, idx) => {
        const isDone     = idx < currentIdx
        const isCurrent  = idx === currentIdx
        const isApproval = stage === 'request_approval'

        return (
          <div key={stage} className="flex items-center gap-2 shrink-0">
            {idx > 0 && (
              <div
                className={cn(
                  'w-6 h-px',
                  isDone || isCurrent ? 'bg-slate-400' : 'bg-slate-200',
                )}
              />
            )}
            <div className="flex flex-col items-center gap-0.5">
              <div
                className={cn(
                  'w-3 h-3 rounded-full border-2 transition-all',
                  isDone    && 'bg-slate-300 border-slate-300',
                  isCurrent && !isApproval && 'bg-blue-500 border-blue-500 ring-2 ring-blue-200 animate-pulse',
                  isCurrent && isApproval  && 'bg-orange-500 border-orange-500 ring-2 ring-orange-200 animate-pulse',
                  !isDone && !isCurrent    && 'bg-background border-slate-300',
                )}
              />
              <span
                className={cn(
                  'text-xs whitespace-nowrap',
                  isCurrent && isApproval
                    ? 'text-orange-600 font-semibold'
                    : 'text-slate-500',
                )}
              >
                {STAGE_LABELS[stage] ?? stage}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
