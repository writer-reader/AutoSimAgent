// frontend/src/steps/Step1Import.tsx
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileUp, FolderOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAppStore } from '@/store/app'
import { api } from '@/api/client'
import type { ApiError } from '@/types'

export function Step1Import() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [manualPath, setManualPath] = useState('')
  const [showManual, setShowManual] = useState(false)
  const [loading, setLoading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const setPaperInfo   = useAppStore(s => s.setPaperInfo)
  const setImportError = useAppStore(s => s.setImportError)
  const setStartError  = useAppStore(s => s.setStartError)
  const setTaskId      = useAppStore(s => s.setTaskId)
  const setStep        = useAppStore(s => s.setStep)
  const navigate       = useNavigate()
  const importError    = useAppStore(s => s.importError)
  const startError     = useAppStore(s => s.startError)
  const storedPaperId  = useAppStore(s => s.paperId)
  const storedPdfPath  = useAppStore(s => s.pdfPath)

  const chosen = selectedFile || (manualPath.trim() ? manualPath.trim() : null)

  function pickFile(file: File | null) {
    setSelectedFile(file)
    setManualPath('')
    setImportError(null)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) {
      if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        setImportError('只支持 PDF 文件')
        return
      }
      pickFile(file)
    }
  }

  async function handleSubmit() {
    if (!chosen) return
    setLoading(true)
    setImportError(null)
    setStartError(null)

    try {
      // Step A: 导入论文（上传文件 或 服务端本地路径）
      let imported
      if (selectedFile) {
        imported = await api.paperUpload(selectedFile)
      } else {
        imported = await api.paperImport({ local_path: manualPath.trim() })
      }
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
      navigate(`/tasks/${task.task_id}`)
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
    <div className="max-w-xl mx-auto space-y-8">
      {/* 页面标题 */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">导入论文</h1>
        <p className="mt-1 text-sm text-muted-foreground">选择本地 PDF，启动分析流水线</p>
      </div>

      <div className="space-y-4">
        {/* 文件选择 / 拖拽区 */}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={e => pickFile(e.target.files?.[0] ?? null)}
        />
        <div
          onDrop={handleDrop}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl py-10 px-8 text-center cursor-pointer transition-colors ${
            dragging
              ? 'border-blue-400 bg-blue-50/50 dark:bg-blue-950/20'
              : 'border-border hover:border-muted-foreground/40'
          }`}
        >
          {selectedFile ? (
            <>
              <FolderOpen className="w-7 h-7 text-blue-500 mx-auto mb-2.5" strokeWidth={1.5} />
              <p className="text-sm font-medium text-foreground">{selectedFile.name}</p>
              <p className="text-xs mt-1 text-muted-foreground">
                {(selectedFile.size / 1024 / 1024).toFixed(2)} MB · 点击重新选择
              </p>
            </>
          ) : (
            <>
              <FileUp className="w-7 h-7 text-muted-foreground/40 mx-auto mb-2.5" strokeWidth={1.5} />
              <p className="text-sm text-muted-foreground">点击选择 PDF 文件，或拖拽到此处</p>
              <p className="text-xs mt-1 text-muted-foreground/50">支持本机与服务端两种部署</p>
            </>
          )}
        </div>

        {/* 手动路径（高级选项，折叠） */}
        <div className="space-y-1.5">
          <button
            type="button"
            onClick={() => setShowManual(s => !s)}
            className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
          >
            {showManual ? '▾ 收起手动输入' : '▸ 或手动输入服务端路径'}
          </button>
          {showManual && (
            <div className="space-y-1.5">
              <Label htmlFor="path-input" className="text-sm font-medium">本地文件路径（服务端可访问）</Label>
              <Input
                id="path-input"
                value={manualPath}
                onChange={e => { setManualPath(e.target.value); setSelectedFile(null) }}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                placeholder="C:\Users\...\paper.pdf"
                className="h-10"
                disabled={loading}
              />
            </div>
          )}
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
          disabled={loading || !chosen}
          className="w-full h-10"
        >
          {loading ? '处理中…' : '开始导入并运行'}
        </Button>
      </div>
    </div>
  )
}
