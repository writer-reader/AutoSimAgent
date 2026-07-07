// frontend/src/api/client.ts
import axios from 'axios'
import type {
  PaperImportRequest, PaperImportResponse,
  WorkflowStartRequest, TaskStatusResponse,
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
      null,
      { params: { approved, ...(editedCode && { edited_code: editedCode }), ...(interruptKey && { interrupt_key: interruptKey }) } }
    ).then(r => r.data),

  taskStatus: (taskId: string) =>
    http.get<TaskStatusResponse>(`/tasks/${taskId}`).then(r => r.data),

  codeContent: (taskId: string, filename: string) =>
    http.get<string>(`/workflow/${taskId}/code/${filename}`, { responseType: 'text' }).then(r => r.data),
}

/** axios response interceptor: surface 4xx JSON body as ApiError */
http.interceptors.response.use(
  r => r,
  err => {
    const data = err.response?.data
    if (data && typeof data.code === 'string') {
      return Promise.reject(data)
    }
    return Promise.reject({ code: 'unknown', message: String(err.message), retryable: false })
  }
)
