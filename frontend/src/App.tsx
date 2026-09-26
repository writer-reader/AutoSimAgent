// frontend/src/App.tsx
import { useEffect, useState } from 'react'
import { Activity, Bot, ClipboardCheck, FilePlus2, FileUp, History } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { api } from '@/api/client'
import { Step1Import } from '@/steps/Step1Import'
import { Step2Pipeline } from '@/steps/Step2Pipeline'
import { Step3Result } from '@/steps/Step3Result'
import { TaskSidebar } from '@/components/TaskSidebar'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ThemeToggle } from '@/components/ThemeToggle'
import { SystemStatus } from '@/components/SystemStatus'

const SESSION_KEY = 'control_agent_task_id'

const STEP_META = [
  { label: '导入', icon: FileUp },
  { label: '运行', icon: Activity },
  { label: '结果', icon: ClipboardCheck },
] as const

function StepIndicator({ current }: { current: 1 | 2 | 3 }) {
  return (
    <div className="flex items-center gap-2">
      {STEP_META.map((meta, i) => {
        const step = (i + 1) as 1 | 2 | 3
        const done   = step < current
        const active = step === current
        const Icon   = meta.icon
        return (
          <div key={step} className="flex items-center gap-2">
            {i > 0 && (
              <div className={cn('w-8 h-px', done ? 'bg-slate-400' : 'bg-slate-200')} />
            )}
            <div className="flex items-center gap-1.5">
              <div className={cn(
                'w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium tabular-nums',
                done   && 'bg-slate-500 text-white',
                active && 'bg-blue-600 text-white',
                !done && !active && 'bg-slate-100 text-slate-400 border border-slate-200 dark:bg-zinc-800 dark:border-zinc-700',
              )}>
                {done ? '✓' : active ? <Icon className="w-3.5 h-3.5" /> : step}
              </div>
              <span className={cn(
                'hidden sm:inline text-sm',
                active ? 'text-slate-800 dark:text-slate-100 font-medium' : 'text-slate-400',
              )}>
                {meta.label}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function App() {
  const step           = useAppStore(s => s.step)
  const setStep        = useAppStore(s => s.setStep)
  const startNewTask   = useAppStore(s => s.startNewTask)
  const setTaskId      = useAppStore(s => s.setTaskId)
  const setTaskStatus  = useAppStore(s => s.setTaskStatus)
  const setFinalResult = useAppStore(s => s.setFinalResult)
  const setStep2Error  = useAppStore(s => s.setStep2Error)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // 刷新恢复：mount 时查询 sessionStorage 中的 taskId
  useEffect(() => {
    const savedId = sessionStorage.getItem(SESSION_KEY)
    if (!savedId) return
    api.taskStatus(savedId).then(task => {
      setTaskId(task.task_id)
      setTaskStatus(task.status)
      switch (task.status) {
        case 'completed':
          if (task.result) setFinalResult(task.result, 'completed')
          setStep(3)
          break
        case 'failed':
          if (task.error) setStep2Error(task.error)
          setStep(2)
          break
        case 'interrupted':
        case 'awaiting_approval':
        case 'running':
        case 'created':
          setStep(2)
          break
      }
    }).catch(() => {
      // 404 或网络错误：任务已过期，清空 sessionStorage
      sessionStorage.removeItem(SESSION_KEY)
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 切步回顶：CodePanel/日志等组件可能把页面滚到中部，换步时归位
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [step])

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b sticky top-0 z-20 bg-background/95 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center gap-3">
          <button
            className="lg:hidden p-2 -ml-2 rounded-md text-slate-500 hover:bg-slate-100 dark:hover:bg-zinc-800 focus-visible:ring-2 focus-visible:ring-blue-500"
            onClick={() => setDrawerOpen(true)}
            aria-label="打开任务记录"
          >
            <History className="w-4.5 h-4.5" />
          </button>
          <div className="flex items-center gap-2.5">
            <span className="w-6 h-6 rounded-md bg-blue-600 text-white flex items-center justify-center shadow-sm">
              <Bot className="w-4 h-4" />
            </span>
            <span className="font-semibold tracking-tight text-foreground">AutoSimAgent</span>
          </div>
          <div className="mx-auto"><StepIndicator current={step} /></div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5"
              onClick={startNewTask}
            >
              <FilePlus2 className="w-4 h-4" />
              <span className="hidden sm:inline">新建任务</span>
            </Button>
            <SystemStatus />
            <a
              href="/landing/index.html"
              target="_blank"
              rel="noopener"
              className="hidden md:inline-block text-xs text-slate-400 hover:text-slate-600 dark:text-zinc-500 dark:hover:text-zinc-300 px-1"
            >
              产品主页
            </a>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* 主体：任务侧栏 + 内容区 */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex">
        {/* 桌面侧栏 */}
        <aside className="hidden lg:block w-60 shrink-0 border-r pr-4">
          <div className="sticky top-14 h-[calc(100vh-3.5rem)]">
            <TaskSidebar />
          </div>
        </aside>

        {/* 内容区 — 流宽版心：宽度交给各 Step 自定（Step1 窄表单居中，Step2/3 工作台双栏） */}
        <main key={step} className="flex-1 min-w-0 px-0 sm:px-6 py-8 lg:py-10 animate-in fade-in duration-150">
          {step === 1 && <Step1Import />}
          {step === 2 && <Step2Pipeline />}
          {step === 3 && <Step3Result />}
        </main>
      </div>

      {/* 移动端抽屉 */}
      {drawerOpen && (
        <div className="lg:hidden fixed inset-0 z-30" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/30" onClick={() => setDrawerOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-72 bg-background border-r shadow-xl animate-in slide-in-from-left duration-150">
            <TaskSidebar onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      )}
    </div>
  )
}
