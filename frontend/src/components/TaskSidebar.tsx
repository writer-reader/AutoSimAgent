// frontend/src/components/TaskSidebar.tsx
// 任务历史侧栏：列出全部任务（时间倒序），点选恢复到对应步骤。
// 版式遵循 Dense 家族准则：信息前置、小字号高密度行；组间距 > 行间距，标题上方留白大于下方。
import { useEffect } from 'react'
import { FilePlus2, History } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { TaskListItem } from '@/types'

const STATUS_META: Record<string, { label: string; dot: string; text: string }> = {
  running:           { label: '运行中',   dot: 'bg-blue-500 animate-pulse',          text: 'text-blue-600 dark:text-blue-400' },
  awaiting_approval: { label: '待审批',   dot: 'bg-orange-500',                      text: 'text-orange-600 dark:text-orange-400' },
  completed:         { label: '已完成',   dot: 'bg-emerald-500',                     text: 'text-emerald-600 dark:text-emerald-400' },
  failed:            { label: '失败',     dot: 'bg-red-500',                         text: 'text-red-600 dark:text-red-400' },
  interrupted:       { label: '已中断',   dot: 'bg-amber-500',                       text: 'text-amber-600 dark:text-amber-400' },
  created:           { label: '已创建',   dot: 'bg-slate-400',                       text: 'text-slate-500' },
}

function relativeTime(ts: number) {
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}

function shortPaper(paperId: string) {
  return paperId.replace(/^paper_/, '').slice(0, 8)
}

function TaskRow({ task, active, onSelect }: {
  task: TaskListItem
  active: boolean
  onSelect: (id: string) => void
}) {
  const meta = STATUS_META[task.status] ?? STATUS_META.created
  return (
    <button
      onClick={() => onSelect(task.task_id)}
      className={cn(
        'w-full text-left px-3 py-2 rounded-lg transition-colors',
        'hover:bg-slate-100/80 dark:hover:bg-zinc-800/60',
        active && 'bg-slate-100 dark:bg-zinc-800 ring-1 ring-slate-300 dark:ring-zinc-600',
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', meta.dot)} />
        <span className={cn('text-xs font-medium truncate', active ? 'text-foreground' : 'text-slate-700 dark:text-slate-200')}>
          {shortPaper(task.paper_id)}
        </span>
        <span className="ml-auto text-[10px] text-slate-400 shrink-0 tabular-nums">{relativeTime(task.updated_at)}</span>
      </div>
      <div className="mt-0.5 pl-3.5 flex items-center gap-1.5">
        <span className={cn('text-[10px]', meta.text)}>{meta.label}</span>
        {task.error && task.status === 'failed' && (
          <span className="text-[10px] text-slate-400 truncate" title={task.error}>{task.error.slice(0, 26)}…</span>
        )}
      </div>
    </button>
  )
}

export function TaskSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const history       = useAppStore(s => s.taskHistory)
  const loadHistory   = useAppStore(s => s.loadTaskHistory)
  const selectTask    = useAppStore(s => s.selectTask)
  const startNewTask  = useAppStore(s => s.startNewTask)
  const currentTaskId = useAppStore(s => s.taskId)

  // 挂载拉取 + 10s 轻轮询（状态徽标随任务推进刷新）
  useEffect(() => {
    loadHistory()
    const t = setInterval(loadHistory, 10_000)
    return () => clearInterval(t)
  }, [loadHistory])

  async function handleSelect(id: string) {
    await selectTask(id)
    onNavigate?.()
  }

  function handleNew() {
    startNewTask()
    onNavigate?.()
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 pt-5 pb-3">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start gap-2 h-8 text-slate-600 dark:text-zinc-300"
          onClick={handleNew}
        >
          <FilePlus2 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          新建任务
        </Button>
      </div>
      <div className="px-4 pb-2">
        <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
          <History className="w-3 h-3" />
          任务记录
          <span className="ml-auto normal-case tracking-normal tabular-nums">{history.length}</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
        {history.length === 0 && (
          <div className="px-3 py-8 text-xs text-slate-400 text-center">还没有任务记录</div>
        )}
        {history.map(task => (
          <TaskRow
            key={task.task_id}
            task={task}
            active={task.task_id === currentTaskId}
            onSelect={handleSelect}
          />
        ))}
      </div>
    </div>
  )
}
