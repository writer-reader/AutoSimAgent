// frontend/src/components/SystemStatus.tsx
// 后端运行状态实时监测：5s 轮询 /system/status，头部徽标 + 可展开详情面板。
import { useEffect, useRef, useState } from 'react'
import { api } from '@/api/client'
import { cn } from '@/lib/utils'
import type { SystemStatus } from '@/types'

const POLL_INTERVAL_MS = 5_000

function formatUptime(s: number): string {
  const sec = Math.max(0, Math.floor(s))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const r = sec % 60
  if (h > 0) return `${h}时${m}分`
  if (m > 0) return `${m}分${r}秒`
  return `${r}秒`
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

const STATUS_LABELS: Record<string, string> = {
  created: '已创建',
  running: '运行中',
  awaiting_approval: '待审批',
  completed: '已完成',
  failed: '已失败',
}

function StatusRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5">
      <span className="text-xs text-slate-400 shrink-0">{label}</span>
      <span className="text-xs text-slate-700 dark:text-slate-200 text-right">{children}</span>
    </div>
  )
}

export function SystemStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [offline, setOffline] = useState(false)
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    let timer: number | undefined

    const poll = async () => {
      try {
        const s = await api.systemStatus()
        if (!alive) return
        setStatus(s)
        setOffline(false)
      } catch {
        if (alive) setOffline(true)
      } finally {
        if (alive) timer = window.setTimeout(poll, POLL_INTERVAL_MS)
      }
    }
    poll()

    // 点击面板外关闭
    const onDocClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
      document.removeEventListener('mousedown', onDocClick)
    }
  }, [])

  const activeCount = status
    ? status.tasks.active.length
    : 0
  const dotColor = offline
    ? 'bg-red-500'
    : activeCount > 0
      ? 'bg-blue-500 animate-pulse'
      : 'bg-emerald-500'
  const label = offline
    ? '后端离线'
    : activeCount > 0
      ? `运行中 ${activeCount}`
      : '后端正常'
  const matlabOk = status?.matlab_mcp.session_alive ?? false

  return (
    <div className="relative" ref={boxRef}>
      <button
        onClick={() => setOpen(o => !o)}
        className={cn(
          'flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs transition-colors',
          offline
            ? 'border-red-200 bg-red-50 text-red-600 dark:border-red-900 dark:bg-red-950/40'
            : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-slate-300',
        )}
        title="后端运行状态（每 5 秒刷新）"
      >
        <span className={cn('w-1.5 h-1.5 rounded-full', dotColor)} />
        <span className="font-medium">{label}</span>
        <span className="text-slate-400">{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-9 z-50 w-80 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg p-3.5">
          {!status ? (
            <div className="text-xs text-slate-400 py-4 text-center">
              {offline ? '无法连接后端' : '加载中…'}
            </div>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-zinc-800">
              <div className="pb-1.5">
                <StatusRow label="服务">
                  <span className="font-medium">
                    {status.app} v{status.version}
                  </span>
                </StatusRow>
                <StatusRow label="运行时长">{formatUptime(status.uptime_s)}</StatusRow>
                <StatusRow label="进程">
                  PID {status.pid} · Python {status.python}
                </StatusRow>
              </div>

              <div className="py-1.5">
                <StatusRow label="任务统计">
                  {status.tasks.total === 0 ? (
                    <span className="text-slate-400">暂无任务</span>
                  ) : (
                    <span>
                      共 {status.tasks.total}
                      {Object.entries(status.tasks.by_status)
                        .sort(([, a], [, b]) => b - a)
                        .map(([k, v]) => ` · ${STATUS_LABELS[k] ?? k} ${v}`)
                        .join('')}
                    </span>
                  )}
                </StatusRow>
                <StatusRow label="活跃任务">
                  {status.tasks.active.length === 0 ? (
                    <span className="text-slate-400">无</span>
                  ) : (
                    <span className="space-y-0.5">
                      {status.tasks.active.map(a => (
                        <div key={a.task_id} className="font-mono text-[11px] text-blue-600">
                          {a.task_id.replace('task_', '')} · {STATUS_LABELS[a.status] ?? a.status}
                          {a.stage ? ` · ${a.stage}` : ''}
                        </div>
                      ))}
                    </span>
                  )}
                </StatusRow>
              </div>

              <div className="py-1.5">
                <StatusRow label="MATLAB MCP">
                  {matlabOk ? (
                    <span className="text-emerald-600">● 已连接</span>
                  ) : status?.matlab_mcp.initialized ? (
                    <span className="text-amber-600">● 已初始化未就绪</span>
                  ) : (
                    <span className="text-slate-400">○ 未启动（任务运行时拉起）</span>
                  )}
                </StatusRow>
                <StatusRow label="LLM">
                  {status.llm.configured ? (
                    <span>
                      {status.llm.default_model}
                      <span className="text-slate-400"> @ {status.llm.base_url_host}</span>
                    </span>
                  ) : (
                    <span className="text-red-500">未配置（缺 .env）</span>
                  )}
                </StatusRow>
              </div>

              <div className="pt-1.5">
                <StatusRow label="事件库">
                  {formatSize(status.db.size_bytes)} · {status.events_total} 条事件
                </StatusRow>
                <StatusRow label="库路径">
                  <span className="font-mono text-[11px]">{status.db.path}</span>
                </StatusRow>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
