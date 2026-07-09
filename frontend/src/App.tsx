// frontend/src/App.tsx
import { useEffect } from 'react'
import { useAppStore } from '@/store/app'
import { api } from '@/api/client'
import { Step1Import } from '@/steps/Step1Import'
import { Step2Pipeline } from '@/steps/Step2Pipeline'
import { Step3Result } from '@/steps/Step3Result'
import { cn } from '@/lib/utils'
import { ThemeToggle } from '@/components/ThemeToggle'

const SESSION_KEY = 'control_agent_task_id'

const STEP_LABELS = ['导入', '运行', '结果'] as const

function StepIndicator({ current }: { current: 1 | 2 | 3 }) {
  return (
    <div className="flex items-center gap-2">
      {STEP_LABELS.map((label, i) => {
        const step = (i + 1) as 1 | 2 | 3
        const done   = step < current
        const active = step === current
        return (
          <div key={step} className="flex items-center gap-2">
            {i > 0 && (
              <div className={cn('w-8 h-px', done ? 'bg-slate-400' : 'bg-slate-200')} />
            )}
            <div className="flex items-center gap-1.5">
              <div className={cn(
                'w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium',
                done   && 'bg-slate-500 text-white',
                active && 'bg-blue-600 text-white',
                !done && !active && 'bg-slate-100 text-slate-400 border border-slate-200',
              )}>
                {done ? '✓' : step}
              </div>
              <span className={cn(
                'text-sm',
                active ? 'text-slate-800 font-medium' : 'text-slate-400',
              )}>
                {label}
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
  const setTaskId      = useAppStore(s => s.setTaskId)
  const setFinalResult = useAppStore(s => s.setFinalResult)
  const setStep2Error  = useAppStore(s => s.setStep2Error)

  // 刷新恢复：mount 时查询 sessionStorage 中的 taskId
  useEffect(() => {
    const savedId = sessionStorage.getItem(SESSION_KEY)
    if (!savedId) return

    api.taskStatus(savedId).then(task => {
      setTaskId(task.task_id)
      switch (task.status) {
        case 'completed':
          if (task.result) setFinalResult(task.result, 'completed')
          setStep(3)
          break
        case 'failed':
          if (task.error) setStep2Error(task.error)
          setStep(2)
          break
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

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-semibold tracking-tight text-foreground">AutoSimAgent</span>
          </div>
          <StepIndicator current={step} />
          <ThemeToggle />
        </div>
      </header>

      {/* 内容区 — 统一版心 */}
      <main key={step} className="max-w-3xl mx-auto px-6 py-10 animate-in fade-in duration-150">
        {step === 1 && <Step1Import />}
        {step === 2 && <Step2Pipeline />}
        {step === 3 && <Step3Result />}
      </main>
    </div>
  )
}
