// frontend/src/components/ApprovalDialog.tsx
import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { CodePanel } from './CodePanel'
import { useAppStore } from '@/store/app'
import { api } from '@/api/client'
import type { ApiError } from '@/types'

export function ApprovalDialog() {
  const payload       = useAppStore(s => s.approvalPayload)
  const count         = useAppStore(s => s.approvalCount)
  const interruptKey  = useAppStore(s => s.currentInterruptKey)
  const taskId        = useAppStore(s => s.taskId)
  const clearApproval = useAppStore(s => s.clearApproval)

  const [editedCode, setEditedCode] = useState<string>('')
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)

  const originalCode = payload?.code ?? ''
  const currentCode  = editedCode || originalCode

  if (!payload || !taskId) return null

  async function handleResume(approved: boolean) {
    setLoading(true)
    setError(null)
    try {
      await api.workflowResume(
        taskId!,
        approved,
        approved ? currentCode : undefined,
        interruptKey ?? undefined,
      )
      clearApproval()
      setEditedCode('')
    } catch (e) {
      const err = e as ApiError
      setError(err.message ?? '请求失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open onOpenChange={() => {}}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="text-orange-600">
            请审核：{payload.tool}
          </DialogTitle>
          <p className="text-xs text-slate-500">第 {count} 次审批</p>
        </DialogHeader>

        <CodePanel
          language={payload.language}
          value={currentCode}
          onChange={setEditedCode}
          onReset={() => setEditedCode('')}
          height="400px"
        />

        {error && (
          <p className="text-sm text-red-600">{error}</p>
        )}

        <DialogFooter>
          <Button
            variant="destructive"
            disabled={loading}
            onClick={() => handleResume(false)}
          >
            拒绝重规划
          </Button>
          <Button
            disabled={loading}
            onClick={() => handleResume(true)}
          >
            批准执行
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
