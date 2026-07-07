// frontend/src/steps/Step3Result.tsx
import { useEffect, useState } from 'react'
import { useAppStore } from '@/store/app'
import { CodePanel } from '@/components/CodePanel'
import { Button } from '@/components/ui/button'
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { api } from '@/api/client'
import { cn } from '@/lib/utils'

export function Step3Result() {
  const result    = useAppStore(s => s.finalResult)
  const criteria  = useAppStore(s => s.criteria)
  const taskId    = useAppStore(s => s.taskId)
  const status    = useAppStore(s => s.taskStatus)
  const clearTask = useAppStore(s => s.clearTask)
  const setStep   = useAppStore(s => s.setStep)

  const [codeContent, setCodeContent] = useState<Record<string, string>>({})
  const [detailOpen,  setDetailOpen]  = useState(false)

  const isSuccess = status === 'completed'

  // Load each code_path's content
  useEffect(() => {
    if (!taskId || !result?.code_paths?.length) return
    result.code_paths.forEach(async (fullPath) => {
      const filename = fullPath.split(/[\\/]/).pop() ?? fullPath
      try {
        const content = await api.codeContent(taskId, filename)
        setCodeContent(prev => ({ ...prev, [filename]: content }))
      } catch {
        setCodeContent(prev => ({ ...prev, [filename]: '// 无法加载代码内容' }))
      }
    })
  }, [taskId, result?.code_paths])

  function handleDownload(filename: string, content: string) {
    const blob = new Blob([content], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  function handleRestart() {
    clearTask()
    setStep(1)
  }

  // Build criteria pass/fail map keyed by criteria_id
  const criteriaMap = Object.fromEntries(
    (result?.verification?.criteria_results ?? []).map(r => [r.criteria_id, r])
  )

  return (
    <div className="max-w-3xl mx-auto mt-8 space-y-6">
      {/* Title */}
      <div>
        <h2 className={cn(
          'text-2xl font-semibold',
          isSuccess ? 'text-slate-800' : 'text-red-700',
        )}>
          {isSuccess ? '✅ 流水线完成' : '❌ 流水线失败'}
        </h2>
        {result?.verdict && (
          <p className="text-sm text-slate-500 mt-1">{result.verdict}</p>
        )}
      </div>

      {/* Acceptance criteria */}
      {criteria.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-700 mb-2">验收标准</h3>
          <div className="space-y-1.5">
            {criteria.map(c => {
              const res = criteriaMap[c.criteria_id]
              const passed = res?.passed
              return (
                <div key={c.criteria_id} className="flex items-start gap-2 text-sm">
                  <span className="mt-0.5 shrink-0">
                    {res === undefined ? '⬜' : passed ? '✅' : '❌'}
                  </span>
                  <span className={cn(
                    passed === false ? 'text-red-600' : 'text-slate-700'
                  )}>
                    {c.description}
                    {res?.detail && (
                      <span className="text-slate-400 ml-1">— {res.detail}</span>
                    )}
                  </span>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Generated code files */}
      {result?.code_paths?.map(fullPath => {
        const filename = fullPath.split(/[\\/]/).pop() ?? fullPath
        const content  = codeContent[filename]
        return (
          <section key={filename}>
            <h3 className="text-sm font-semibold text-slate-700 mb-2">{filename}</h3>
            {content !== undefined ? (
              <CodePanel
                language="matlab"
                value={content}
                readOnly
                onDownload={() => handleDownload(filename, content)}
              />
            ) : (
              <div className="text-sm text-slate-400 py-4 text-center">加载中…</div>
            )}
          </section>
        )
      })}

      {/* Process details (collapsible) */}
      {result && (
        <Collapsible open={detailOpen} onOpenChange={setDetailOpen}>
          <CollapsibleTrigger asChild>
            <button className="text-xs text-slate-400 hover:text-slate-600 underline">
              {detailOpen ? '收起' : '展开'}过程详情
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-2 text-xs text-slate-500 space-y-1 pl-2 border-l border-slate-200">
              <div>校准轮次：{result.calib_rounds}</div>
              <div>工具调用次数：{result.tool_calls}</div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      <Button variant="outline" onClick={handleRestart}>
        重新运行另一篇
      </Button>
    </div>
  )
}
