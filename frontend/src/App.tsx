// frontend/src/App.tsx
// 应用壳：header + 左导航 rail + 主内容区（React Router 切换视图）。
// 视图：/ 工作台（无活动任务时是新建面板，有则显示当前任务）·
//       /tasks/:taskId 任务详情（URL 为唯一事实来源）·
//       /papers 论文库（Phase 2）。
// 全局三步指示器退场：阶段感收进任务详情内部，导航与恢复语义由 URL 承担。
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { Bot, History, Link2, SearchX } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { Step1Import } from '@/steps/Step1Import'
import { Step2Pipeline } from '@/steps/Step2Pipeline'
import { Step3Result } from '@/steps/Step3Result'
import { TaskSidebar } from '@/components/TaskSidebar'
import { PapersPage } from '@/pages/PapersPage'
import { ThemeToggle } from '@/components/ThemeToggle'
import { SystemStatus } from '@/components/SystemStatus'

// 任务详情内容：按内部阶段渲染（运行中/中断 → Step2，已结算 → Step3）
function TaskDetailContent() {
  const step        = useAppStore(s => s.step)
  const finalResult = useAppStore(s => s.finalResult)
  if (step === 3 && finalResult) return <Step3Result />
  return <Step2Pipeline />
}

// 工作台首页：有活动任务时回到它的详情，否则是新建面板
function WorkbenchHome() {
  const taskId = useAppStore(s => s.taskId)
  const step   = useAppStore(s => s.step)
  if (taskId && step > 1) return <TaskDetailContent />
  return <Step1Import />
}

// 任务详情页：taskId 在 URL 里。store 中已加载的（活动/运行中）直接渲染；
// 否则按参数从服务端恢复（刷新 / 分享链接 / 侧栏点选共用这一条路径）。
function TaskDetailPage() {
  const { taskId = '' } = useParams()
  const storeTaskId  = useAppStore(s => s.taskId)
  const loadTaskById = useAppStore(s => s.loadTaskById)
  const [state, setState] = useState<'loading' | 'ready' | 'missing'>(
    storeTaskId === taskId ? 'ready' : 'loading',
  )
  // 本挂载已经处理过的 taskId：store 被清空（删除当前任务/新建任务）时不重拉已离开的任务
  const handledRef = useRef<string | null>(storeTaskId === taskId ? taskId : null)

  useEffect(() => {
    if (handledRef.current === taskId) return
    if (storeTaskId === taskId) {
      handledRef.current = taskId
      setState('ready')
      return
    }
    const ac = new AbortController()
    setState('loading')
    loadTaskById(taskId, ac.signal)
      .then(() => {
        if (ac.signal.aborted) return
        handledRef.current = taskId
        setState('ready')
      })
      .catch(() => { if (!ac.signal.aborted) setState('missing') })
    return () => ac.abort()
  }, [taskId, storeTaskId, loadTaskById])

  if (state === 'loading') return <TaskDetailSkeleton />
  if (state === 'missing') return <TaskNotFound taskId={taskId} />
  return <TaskDetailContent />
}

function TaskDetailSkeleton() {
  return (
    <div className="max-w-3xl space-y-6" aria-busy="true">
      <div className="h-8 w-64 rounded-md bg-muted animate-pulse" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px rounded-xl border border-border overflow-hidden">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="bg-card px-4 py-3 space-y-2">
            <div className="h-3 w-14 rounded bg-muted animate-pulse" />
            <div className="h-5 w-20 rounded bg-muted animate-pulse" />
          </div>
        ))}
      </div>
      <div className="h-64 rounded-xl border border-border bg-card p-4 space-y-3">
        <div className="h-4 w-24 rounded bg-muted animate-pulse" />
        <div className="h-3 w-full rounded bg-muted/70 animate-pulse" />
        <div className="h-3 w-4/5 rounded bg-muted/70 animate-pulse" />
        <div className="h-3 w-3/5 rounded bg-muted/70 animate-pulse" />
      </div>
    </div>
  )
}

function TaskNotFound({ taskId }: { taskId: string }) {
  return (
    <div className="max-w-md mx-auto text-center py-16 space-y-4">
      <div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center">
        <SearchX className="w-6 h-6 text-muted-foreground" />
      </div>
      <div>
        <h1 className="text-lg font-semibold text-foreground">任务不存在或已被清理</h1>
        <p className="mt-1 text-sm text-muted-foreground break-all">
          {taskId ? `没有找到 ${taskId} 的记录` : '任务地址无效'}
        </p>
      </div>
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline"
      >
        <Link2 className="w-4 h-4" />
        回到工作台新建任务
      </Link>
    </div>
  )
}

export default function App() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  // 路由切换回顶（详情页长内容会把页面滚到中部）
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [location.pathname])

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b sticky top-0 z-20 bg-background/95 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center gap-3">
          <button
            className="lg:hidden p-2 -ml-2 rounded-md text-slate-500 hover:bg-slate-100 dark:hover:bg-zinc-800 focus-visible:ring-2 focus-visible:ring-blue-500"
            onClick={() => setDrawerOpen(true)}
            aria-label="打开导航"
          >
            <History className="w-4.5 h-4.5" />
          </button>
          <Link to="/" className="flex items-center gap-2.5 rounded-md focus-visible:ring-2 focus-visible:ring-blue-500">
            <span className="w-6 h-6 rounded-md bg-blue-600 text-white flex items-center justify-center shadow-sm">
              <Bot className="w-4 h-4" />
            </span>
            <span className="font-semibold tracking-tight text-foreground">AutoSimAgent</span>
          </Link>
          <div className="ml-auto flex items-center gap-2">
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

      {/* 主体：导航 rail + 内容区 */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex">
        {/* 桌面 rail */}
        <aside className="hidden lg:block w-60 shrink-0 border-r pr-4">
          <div className="sticky top-14 h-[calc(100vh-3.5rem)]">
            <TaskSidebar />
          </div>
        </aside>

        {/* 内容区 — 流宽版心：宽度交给各视图自定（新建面板窄居中，工作台/结果双栏） */}
        <main
          key={location.pathname}
          className="flex-1 min-w-0 px-0 sm:px-6 py-8 lg:py-10 animate-in fade-in slide-in-from-bottom-1 duration-200 motion-reduce:animate-none"
        >
          <Routes>
            <Route path="/" element={<WorkbenchHome />} />
            <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
            <Route path="/papers" element={<PapersPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
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
