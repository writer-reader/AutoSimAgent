// frontend/src/components/TaskSidebar.tsx
// 左导航 rail：新建任务（唯一入口）→ 视图切换（工作台 / 论文库）→ 任务记录（最近任务，滚动）。
// 版式遵循 Dense 家族准则：信息前置、小字号高密度行；导航件用着色内嵌面板，与右侧内容卡的描边卡片语言区分。
import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { FilePlus2, History, LayoutDashboard, LibraryBig, Trash2, TriangleAlert } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { api } from '@/api/client'
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

function TaskRow({ task, active, onSelect, onDelete }: {
  task: TaskListItem
  active: boolean
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}) {
  const meta = STATUS_META[task.status] ?? STATUS_META.created
  const [confirming, setConfirming] = useState(false)

  // 二次点击确认：2.6s 内再点一次才真删，超时自动还原，不用弹窗打断
  useEffect(() => {
    if (!confirming) return
    const t = setTimeout(() => setConfirming(false), 2600)
    return () => clearTimeout(t)
  }, [confirming])

  return (
    <div className={cn(
      'relative group rounded-md',
      active && 'bg-white dark:bg-zinc-800 ring-1 ring-slate-200 dark:ring-zinc-700',
    )}>
      <button
        onClick={() => onSelect(task.task_id)}
        className={cn(
          'w-full text-left px-2.5 py-2 pr-8 rounded-md transition-colors',
          'hover:bg-slate-50/90 dark:hover:bg-zinc-800/70',
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
      <button
        type="button"
        aria-label={confirming ? '确认删除' : '删除任务'}
        title={confirming ? '再点一次确认删除' : '删除任务'}
        onClick={e => {
          e.stopPropagation()
          if (confirming) onDelete(task.task_id)
          else setConfirming(true)
        }}
        className={cn(
          'absolute right-1.5 top-1.5 p-1 rounded-md transition-all',
          'opacity-100 lg:opacity-0 lg:group-hover:opacity-100 lg:focus-visible:opacity-100',
          confirming
            ? 'text-red-600 bg-red-100/80 dark:bg-red-950/60 dark:text-red-400'
            : 'text-slate-400 hover:text-red-500 hover:bg-slate-200/60 dark:hover:bg-zinc-700/70',
        )}
      >
        {confirming ? <TriangleAlert className="w-3.5 h-3.5" /> : <Trash2 className="w-3.5 h-3.5" />}
      </button>
    </div>
  )
}

export function TaskSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const history       = useAppStore(s => s.taskHistory)
  const loadHistory   = useAppStore(s => s.loadTaskHistory)
  const currentTaskId = useAppStore(s => s.taskId)
  const navigate      = useNavigate()

  // 挂载拉取 + 10s 轻轮询（状态徽标随任务推进刷新）
  useEffect(() => {
    loadHistory()
    const t = setInterval(loadHistory, 10_000)
    return () => clearInterval(t)
  }, [loadHistory])

  function handleSelect(id: string) {
    navigate(`/tasks/${id}`)
    onNavigate?.()
  }

  function handleNew() {
    useAppStore.getState().startNewTask()
    navigate('/')
    onNavigate?.()
  }

  // 删除任务：删的是当前任务时先清空工作区并离开详情页（否则 TaskDetailPage 会对
  // 已删任务重新拉取，把已删内容复活到界面上），再发删除请求；后端拒绝时列表刷新恢复原状。
  async function handleDelete(id: string) {
    if (useAppStore.getState().taskId === id) {
      useAppStore.getState().startNewTask()
      navigate('/')
    }
    try {
      await api.taskDelete(id)
    } catch {
      // 静默：列表刷新后自然回到一致状态
    }
    await loadHistory()
  }

  const navItem = ({ isActive }: { isActive: boolean }) => cn(
    'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-blue-500',
    isActive
      ? 'bg-blue-600/10 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300'
      : 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900 dark:text-zinc-400 dark:hover:bg-zinc-800/60 dark:hover:text-zinc-200',
  )

  return (
    <div className="flex flex-col h-full px-3 pt-5 pb-4">
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-start gap-2 h-8 text-slate-600 dark:text-zinc-300"
        onClick={handleNew}
      >
        <FilePlus2 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
        新建任务
      </Button>
      <nav className="space-y-0.5" aria-label="视图切换">
        <NavLink to="/" end className={navItem} onClick={onNavigate}>
          <LayoutDashboard className="w-4 h-4 shrink-0" />
          工作台
        </NavLink>
        <NavLink to="/papers" className={navItem} onClick={onNavigate}>
          <LibraryBig className="w-4 h-4 shrink-0" />
          论文库
        </NavLink>
      </nav>
      {/* 任务记录：着色内嵌面板（无边框无头栏），与右侧内容卡的描边卡片语言刻意区分 */}
      <div className="px-1 pt-5 pb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
        <History className="w-3 h-3" />
        任务记录
        <span className="ml-auto normal-case tracking-normal tabular-nums">{history.length}</span>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto rounded-lg bg-slate-100/70 dark:bg-zinc-900/60 p-1.5 space-y-0.5">
        {history.length === 0 && (
          <div className="px-3 py-8 text-xs text-slate-400 text-center">还没有任务记录</div>
        )}
          {history.map(task => (
            <TaskRow
              key={task.task_id}
              task={task}
              active={task.task_id === currentTaskId}
              onSelect={handleSelect}
              onDelete={handleDelete}
            />
          ))}
      </div>
    </div>
  )
}
