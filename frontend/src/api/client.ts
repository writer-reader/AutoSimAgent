// frontend/src/api/client.ts
import axios from 'axios'
import type {
  PaperImportRequest, PaperImportResponse,
  WorkflowStartRequest, TaskStatusResponse,
  TaskListResponse, TaskEventsResponse,
  SystemStatus,
  ApiError,
} from '@/types'

const http = axios.create({ baseURL: '/api' })

export const api = {
  paperImport: (req: PaperImportRequest) =>
    http.post<PaperImportResponse>('/papers/import', req).then(r => r.data),

  workflowStart: (req: WorkflowStartRequest) =>
    http.post<TaskStatusResponse>('/workflow/start', req).then(r => r.data),

  workflowStatus: (taskId: string) =>
    http.get<TaskStatusResponse>(`/workflow/${taskId}`).then(r => r.data),

  workflowResume: (taskId: string, approved: boolean, editedCode?: string, interruptKey?: string) =>
    http.post<TaskStatusResponse>(
      `/workflow/${taskId}/resume`,
      {
        ...(editedCode !== undefined && { edited_code: editedCode }),
        ...(interruptKey !== undefined && { interrupt_key: interruptKey }),
      },
      { params: { approved } }
    ).then(r => r.data),

  taskStatus: (taskId: string) =>
    http.get<TaskStatusResponse>(`/tasks/${taskId}`).then(r => r.data),

  taskList: (params?: { status?: string; limit?: number }) =>
    http.get<TaskListResponse>('/tasks', { params }).then(r => r.data),

  // 任务事件回放（M0 断线补传端点）：恢复历史任务时用它补拉最终验收明细
  taskEvents: (taskId: string, afterSeq = 0) =>
    http.get<TaskEventsResponse>(`/tasks/${taskId}/events`, { params: { after_seq: afterSeq, limit: 5000 } }).then(r => r.data),

  // 删除任务记录及其事件流（运行中的任务后端拒绝；产物文件保留在磁盘）
  taskDelete: (taskId: string) =>
    http.delete<{ task_id: string; deleted: boolean }>(`/tasks/${taskId}`).then(r => r.data),

  codeContent: (taskId: string, filename: string) =>
    http.get<string>(`/workflow/${taskId}/code/${filename}`, { responseType: 'text' }).then(r => r.data),

  // 产物文件 URL（直接用于 <img src>；后端只允许 result.artifacts 中登记过的文件名）
  artifactUrl: (taskId: string, filename: string) =>
    `/api/workflow/${taskId}/artifacts/${encodeURIComponent(filename)}`,

  paperUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<PaperImportResponse>('/papers/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  workflowRestart: (taskId: string) =>
    http.post<TaskStatusResponse>(`/workflow/${taskId}/restart`).then(r => r.data),

  systemStatus: () =>
    http.get<SystemStatus>('/system/status').then(r => r.data),
}

/** axios response interceptor: surface 4xx JSON body as ApiError */
http.interceptors.response.use(
  r => r,
  err => {
    const status = err.response?.status
    const data = err.response?.data
    if (status >= 400 && status < 500 && typeof data?.code === 'string' && typeof data?.message === 'string') {
      return Promise.reject({ code: data.code, message: data.message, retryable: Boolean(data.retryable) } as ApiError)
    }
    return Promise.reject({ code: 'unknown', message: err?.message ?? String(err), retryable: false } as ApiError)
  }
)
