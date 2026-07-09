// frontend/src/steps/Step1Import.tsx
import { useState, useRef } from 'react'
import { FileUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAppStore } from '@/store/app'
import { api } from '@/api/client'
import type { ApiError } from '@/types'

export function Step1Import() {
  const [localPath, setLocalPath] = useState('')
  const [loading,   setLoading]   = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)

  const setPaperInfo   = useAppStore(s => s.setPaperInfo)
  const setImportError = useAppStore(s => s.setImportError)
  const setStartError  = useAppStore(s => s.setStartError)
  const setTaskId      = useAppStore(s => s.setTaskId)
  const setStep        = useAppStore(s => s.setStep)
  const importError    = useAppStore(s => s.importError)
  const startError     = useAppStore(s => s.startError)
  const storedPaperId  = useAppStore(s => s.paperId)
  const storedPdfPath  = useAppStore(s => s.pdfPath)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) {
      // 浏览器拿不到真实路径，只填文件名作为提示
      setLocalPath(file.name)
    }
  }

  async function handleSubmit() {
    if (!localPath.trim()) return
    setLoading(true)
    setImportError(null)
    setStartError(null)

    try {
      // Step A: 导入论文
      const imported = await api.paperImport({ local_path: localPath.trim() })
      setPaperInfo(imported.paper_id, imported.pdf_path)

      // Step B: 启动流水线
      await launchWorkflow(imported.paper_id, imported.pdf_path)
    } catch (e) {
      const err = e as ApiError
      setImportError(err.message ?? '导入失败')
    } finally {
      setLoading(false)
    }
  }

  async function launchWorkflow(paperId: string, pdfPath: string) {
    try {
      const task = await api.workflowStart({
        paper_id: paperId,
        pdf_path: pdfPath,
        user_id: 'local', // demo 临时值，多用户场景需改为实际标识
      })
      setTaskId(task.task_id)
      setStep(2)
    } catch (e) {
      const err = e as ApiError
      setStartError(err.message ?? '启动失败')
    }
  }

  async function handleRetryStart() {
    if (!storedPaperId || !storedPdfPath) return
    setLoading(true)
    setStartError(null)
    try {
      await launchWorkflow(storedPaperId, storedPdfPath)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-8">
      {/* 页面标题 */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">导入论文</h1>
        <p className="mt-1 text-sm text-muted-foreground">粘贴本地 PDF 路径，启动分析流水线</p>
      </div>

      <div className="space-y-4">
        {/* 拖拽提示区 */}
        <div
          ref={dropRef}
          onDrop={handleDrop}
          onDragOver={e => e.preventDefault()}
          className="border-2 border-dashed border-border rounded-xl py-10 px-8 text-center hover:border-muted-foreground/40 transition-colors cursor-pointer"
          onClick={() => document.getElementById('path-input')?.focus()}
        >
          <FileUp className="w-7 h-7 text-muted-foreground/40 mx-auto mb-2.5" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">拖拽 PDF 到此处</p>
          <p className="text-xs mt-1 text-muted-foreground/50">浏览器无法获取完整路径，请在下方手动输入</p>
        </div>

        {/* 路径输入 */}
        <div className="space-y-1.5">
          <Label htmlFor="path-input" className="text-sm font-medium">本地文件路径</Label>
          <Input
            id="path-input"
            value={localPath}
            onChange={e => setLocalPath(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            placeholder="C:\Users\...\paper.pdf"
            className="h-10"
            disabled={loading}
          />
        </div>

        {/* 错误提示 */}
        {importError && (
          <p className="text-sm text-destructive">{importError}</p>
        )}
        {startError && (
          <div className="flex items-center gap-3">
            <p className="text-sm text-destructive">{startError}</p>
            <Button size="sm" variant="outline" onClick={handleRetryStart} disabled={loading}>
              重新启动
            </Button>
          </div>
        )}

        <Button
          onClick={handleSubmit}
          disabled={loading || !localPath.trim()}
          className="w-full h-10"
        >
          {loading ? '处理中…' : '开始导入并运行'}
        </Button>
      </div>
    </div>
  )
}
