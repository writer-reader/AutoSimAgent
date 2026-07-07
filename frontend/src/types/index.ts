// frontend/src/types/index.ts

export interface PaperImportRequest {
  local_path: string
  metadata?: Record<string, string>
}

export interface PaperImportResponse {
  paper_id: string
  pdf_path: string
  file_hash: string
}

export interface WorkflowStartRequest {
  paper_id: string
  pdf_path: string
  user_id: string
}

export interface TaskStatusResponse {
  task_id: string
  status: 'created' | 'running' | 'awaiting_approval' | 'completed' | 'failed'
  stage: string | null
  error: string | null
  result: TaskResult | null
}

export interface TaskResult {
  verification: VerificationResult | null
  verdict: string | null
  code_paths: string[]
  calib_rounds: number
  tool_calls: number
}

export interface VerificationResult {
  criteria_results: CriteriaResult[]
}

export interface CriteriaResult {
  criteria_id: string
  passed: boolean
  detail?: string
}

export interface CriteriaItem {
  criteria_id: string
  description: string
}

export interface InterruptPayload {
  tool: string
  language: string
  code: string
  interrupt_key: string
}

export interface ApiError {
  code: string
  message: string
  retryable: boolean
}

// SSE event types
export type SseEvent =
  | { type: 'stage'; stage: string; label: string; ts?: number }
  | { type: 'node'; stage: string; ts?: number; [k: string]: unknown }
  | { type: 'knowledge_done'; criteria_count: number; criteria?: CriteriaItem[]; ts?: number }
  | { type: 'interrupt'; stage: string; label: string; payload: InterruptPayload; ts?: number }
  | { type: 'resume'; label: string; approved: boolean; ts?: number }
  | { type: 'done'; status: string; result: TaskResult | null; ts?: number }
  | { type: 'error'; error: string; ts?: number }
  | { type: 'heartbeat'; ts?: number }
  | { type: 'unknown'; ts?: number; [k: string]: unknown }
