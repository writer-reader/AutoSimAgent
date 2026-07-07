// frontend/src/steps/Step2Pipeline.tsx
import { useAppStore } from '@/store/app'
import { useWorkflowStream } from '@/hooks/useWorkflowStream'
import { StageProgress } from '@/components/StageProgress'
import { EventLog } from '@/components/EventLog'
import { ApprovalDialog } from '@/components/ApprovalDialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function Step2Pipeline() {
  const taskId     = useAppStore(s => s.taskId)
  const taskStatus = useAppStore(s => s.taskStatus)
  const step2Error = useAppStore(s => s.step2Error)
  const stageLabel = useAppStore(s => s.currentStageLabel)
  const clearTask  = useAppStore(s => s.clearTask)
  const setStep    = useAppStore(s => s.setStep)

  // 挂载时连接 SSE
  useWorkflowStream(taskId)

  const isWaiting  = taskStatus === 'awaiting_approval'
  const isFailed   = !!step2Error

  function handleRestart() {
    clearTask()
    setStep(1)
  }

  return (
    <div className="max-w-3xl mx-auto mt-8 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-800">流水线运行中</h2>
        <span className={cn(
          'text-sm font-medium px-2 py-0.5 rounded-full',
          isFailed   && 'bg-red-100 text-red-700',
          isWaiting  && 'bg-orange-100 text-orange-700',
          !isFailed && !isWaiting && 'bg-blue-100 text-blue-700',
        )}>
          {isFailed ? '❌ 失败' : isWaiting ? '⚠️ 等待审批' : '● 运行中'}
        </span>
      </div>

      {stageLabel && !isFailed && (
        <p className="text-sm text-slate-500">{stageLabel}</p>
      )}

      {/* 阶段进度条 */}
      <StageProgress />

      {/* SSE 日志 */}
      <EventLog />

      {/* 失败态 */}
      {isFailed && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 space-y-2">
          <p className="text-sm text-red-700 font-medium">流水线失败</p>
          <p className="text-sm text-red-600">{step2Error}</p>
          <Button variant="outline" size="sm" onClick={handleRestart}>
            重新运行
          </Button>
        </div>
      )}

      {/* 审批弹层（自包含，读 store 决定显示） */}
      <ApprovalDialog />
    </div>
  )
}
