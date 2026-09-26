// frontend/src/steps/Step2Pipeline.tsx
// 双栏工作台：左列（监控 + 中断/失败卡），右列事件日志（xl+ 满高 sticky，以下回落单栏堆叠）。
import { useState } from 'react'
import { Activity, CircleAlert, CircleUserRound, CircleX, RefreshCw, SquarePlay } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { useWorkflowStream } from '@/hooks/useWorkflowStream'
import { StageProgress } from '@/components/StageProgress'
import { EventLog } from '@/components/EventLog'
import { RunMonitor } from '@/components/RunMonitor'
import { ApprovalDialog } from '@/components/ApprovalDialog'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'

const STATUS_BADGE = {
  running:    { title: '流水线运行中', icon: Activity,        cls: 'text-blue-600 dark:text-blue-400',       iconCls: 'animate-pulse' },
  waiting:    { title: '等待人工审批', icon: CircleUserRound, cls: 'text-orange-600 dark:text-orange-400',   iconCls: 'animate-pulse' },
  interrupted:{ title: '任务已中断',   icon: CircleAlert,     cls: 'text-amber-600 dark:text-amber-400',     iconCls: '' },
  failed:     { title: '流水线失败',   icon: CircleX,         cls: 'text-red-600 dark:text-red-400',         iconCls: '' },
} as const

function StatusBadge({ kind }: { kind: keyof typeof STATUS_BADGE }) {
  const s = STATUS_BADGE[kind]
  const Icon = s.icon
  return (
    <span
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 dark:bg-zinc-800 ${s.cls}`}
      title={s.title}
    >
      <Icon className={`w-4.5 h-4.5 ${s.iconCls}`} />
    </span>
  )
}

export function Step2Pipeline() {
  const taskId        = useAppStore(s => s.taskId)
  const taskStatus    = useAppStore(s => s.taskStatus)
  const step2Error    = useAppStore(s => s.step2Error)
  const stageLabel    = useAppStore(s => s.currentStageLabel)
  const setTaskStatus = useAppStore(s => s.setTaskStatus)
  const setStep2Error = useAppStore(s => s.setStep2Error)
  const clearStep2Error = useAppStore(s => s.clearStep2Error)
  const incStreamNonce = useAppStore(s => s.incStreamNonce)
  const [restoring, setRestoring] = useState(false)

  // 挂载时连接 SSE
  useWorkflowStream(taskId)

  const isWaiting     = taskStatus === 'awaiting_approval'
  const isInterrupted = taskStatus === 'interrupted'
  const isFailed      = !!step2Error

  async function handleResume() {
    if (!taskId) return
    setRestoring(true)
    clearStep2Error()
    try {
      const task = await api.workflowRestart(taskId)
      setTaskStatus(task.status)
      // 事件流在终态时已被关闭，恢复后强制重建连接（从 lastSeq 续传，不重放历史）
      incStreamNonce()
    } catch (e) {
      setStep2Error('从断点恢复失败：' + (e as { message?: string }).message)
    } finally {
      setRestoring(false)
    }
  }

  const statusKind: keyof typeof STATUS_BADGE =
    isFailed ? 'failed' : isWaiting ? 'waiting' : isInterrupted ? 'interrupted' : 'running'

  return (
    <div className="space-y-5">
      {/* 页面标题 */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              {STATUS_BADGE[statusKind].title}
            </h1>
            {taskId && (
              <span className="hidden sm:inline font-mono text-xs text-slate-400 bg-slate-100/80 dark:bg-zinc-800/80 rounded px-1.5 py-0.5 truncate">
                {taskId}
              </span>
            )}
          </div>
          {stageLabel && !isFailed && !isInterrupted && (
            <p className="mt-0.5 text-sm text-muted-foreground">{stageLabel}</p>
          )}
        </div>
        <StatusBadge kind={statusKind} />
      </div>

      {/* 阶段时间线 */}
      <StageProgress />

      {/* 双栏：左 = 监控 + 中断/失败卡；右 = 事件日志（xl+ 满高 sticky） */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] xl:items-start">
        <div className="space-y-5 min-w-0">
          <RunMonitor />

          {/* 中断态：从断点恢复 */}
          {isInterrupted && (
            <div className="rounded-xl bg-amber-50/70 dark:bg-amber-950/30 p-4 space-y-2">
              <p className="text-sm text-amber-700 dark:text-amber-400 font-medium flex items-center gap-1.5">
                <CircleAlert className="w-4 h-4" /> 任务因服务重启中断
              </p>
              <p className="text-sm text-amber-600/90 dark:text-amber-400/90">
                可从最近的 LangGraph 检查点续跑（连回滚中断点都能恢复），或重新开始。
              </p>
              <div className="flex gap-2">
                <Button size="sm" onClick={handleResume} disabled={restoring}>
                  <RefreshCw className="w-3.5 h-3.5" /> {restoring ? '恢复中…' : '从断点恢复'}
                </Button>
              </div>
            </div>
          )}

          {/* 失败态：报错信息 + 从断点/缓存继续（后端按阶段缓存，不从头重跑） */}
          {isFailed && (
            <div className="rounded-xl bg-rose-50/60 dark:bg-rose-950/30 p-4 space-y-2">
              <p className="text-sm text-red-700 dark:text-rose-400 font-medium flex items-center gap-1.5">
                <CircleX className="w-4 h-4" /> 流水线失败
              </p>
              <p className="text-sm text-red-600 dark:text-rose-400 break-all">{step2Error}</p>
              <p className="text-xs text-red-500/80 dark:text-rose-400/70">
                已完成阶段的产物有缓存（PDF 解析 / 知识抽取等不会重跑），可从断点继续。
              </p>
              <div className="flex gap-2">
                <Button size="sm" onClick={handleResume} disabled={restoring}>
                  <RefreshCw className="w-3.5 h-3.5" /> {restoring ? '恢复中…' : '从断点继续'}
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* 右列：SSE 事件日志（sticky 满高） */}
        <div className="xl:sticky xl:top-20 min-w-0">
          <div className="flex items-center gap-2 mb-2 xl:mb-2">
            <SquarePlay className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">事件流 SSE</span>
          </div>
          <EventLog tall />
        </div>
      </div>

      <ApprovalDialog />
    </div>
  )
}
