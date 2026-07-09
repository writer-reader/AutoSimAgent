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
    <div className="space-y-7">
      {/* 标题 */}
      <div>
        <h1 className={cn(
          'text-2xl font-semibold tracking-tight',
          isSuccess ? 'text-foreground' : 'text-destructive',
        )}>
          {isSuccess ? '流水线完成' : '流水线失败'}
        </h1>
        {result?.verdict && (
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">{result.verdict}</p>
        )}
      </div>

      {/* 验收标准 */}
      {criteria.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">验收标准</h2>
          <div className="space-y-1.5">
            {criteria.map(c => {
              const res = criteriaMap[c.criteria_id]
              const passed = res?.passed
              return (
                <div key={c.criteria_id} className={cn(
                  'pl-3 border-l-2 text-sm py-0.5',
                  res === undefined && 'border-border',
                  passed === true  && 'border-emerald-300/60',
                  passed === false && 'border-rose-300/50',
                )}>
                  <span className={cn(
                    res === undefined && 'text-muted-foreground',
                    passed === true   && 'text-foreground',
                    passed === false  && 'text-muted-foreground',
                  )}>
                    {c.description}
                    {res?.detail && (
                      <span className="text-muted-foreground/60 ml-1.5 text-xs">{res.detail}</span>
                    )}
                  </span>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 生成代码 */}
      {result?.code_paths?.map(fullPath => {
        const filename = fullPath.split(/[\\/]/).pop() ?? fullPath
        const content  = codeContent[filename]
        return (
          <section key={filename} className="space-y-2">
            <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{filename}</h2>
            {content !== undefined ? (
              <CodePanel
                language="matlab"
                value={content}
                readOnly
                onDownload={() => handleDownload(filename, content)}
              />
            ) : (
              <div className="text-sm text-muted-foreground py-6 text-center">加载中…</div>
            )}
          </section>
        )
      })}

      {/* 过程详情 */}
      {result && (
        <Collapsible open={detailOpen} onOpenChange={setDetailOpen}>
          <CollapsibleTrigger asChild>
            <button className="text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
              {detailOpen ? '收起' : '展开'}过程详情
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-2 text-xs text-muted-foreground space-y-1 pl-3 border-l border-border">
              <div>校准轮次：{result.calib_rounds}</div>
              <div>工具调用次数：{result.tool_calls}</div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      <Button variant="outline" size="sm" onClick={handleRestart}>
        重新运行另一篇
      </Button>
    </div>
  )
}
