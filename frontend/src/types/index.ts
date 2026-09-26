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
  status: 'created' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'interrupted'
  stage: string | null
  error: string | null
  result: TaskResult | null
  criteria?: { criterion_id: string; description?: string; metric?: string }[] | null
}

export interface TaskListItem {
  task_id: string
  paper_id: string
  status: TaskStatusResponse['status']
  stage: string | null
  error: string | null
  created_at: number
  updated_at: number
}

export interface TaskListResponse {
  items: TaskListItem[]
  total: number
  offset: number
  limit: number
}

export interface TaskResult {
  verification: VerificationResult | null
  verdict: string | null
  code_paths: string[]
  artifacts?: ArtifactItem[]
  calib_rounds: number
  tool_calls: number
}

export interface ArtifactItem {
  kind: string   // figure / data / model
  path: string
  label: string
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

// ── 知识摘要（M0 透明化：knowledge_done 事件携带论文被读成的样子）──
export interface KnowledgeEquation {
  latex?: string
  category?: string
  confidence?: number
  evidence_ref?: string
}
export interface KnowledgeParameter {
  symbol?: string
  value?: string | number | null
  unit?: string | null
  confidence?: number
  evidence_ref?: string
}
export interface KnowledgeController {
  type?: string
  architecture?: string
  confidence?: number
  evidence_ref?: string
}
export interface KnowledgeSummary {
  equations?: KnowledgeEquation[]
  parameters?: KnowledgeParameter[]
  controllers?: KnowledgeController[]
  equation_count?: number
  parameter_count?: number
  controller_count?: number
}

export interface ToolResult {
  seq: number
  ok: boolean
  stdout_tail: string
  stderr_tail: string
  artifacts: { kind: string; path: string; label: string }[]
  error_layer?: string | null
}
// verify 节点对单条验收指标的裁决：expected/actual 是真实结算值，
// hardcoded 表示被硬编码/作弊检查标红（代码含与期望一致的字面量）。
export interface VerdictCriterionResult {
  metric?: string
  expected?: number | boolean | string | null
  actual?: number | boolean | string | null
  relation?: string
  passed?: boolean
  reason?: string
  hardcoded?: boolean
}

export interface Verdict {
  passed?: boolean
  summary?: string
  results?: VerdictCriterionResult[]
}

// GET /tasks/{id}/events（断线补传 / 恢复任务时补拉最终验收明细）
export interface TaskEventEntry {
  seq: number
  type: string
  data: SseEvent
}
export interface TaskEventsResponse {
  task_id: string
  after_seq: number
  events: TaskEventEntry[]
}

// ── 系统运行状态（/system/status，实时监测轮询）──
export interface SystemStatus {
  status: string
  app: string
  version: string
  pid: number
  python: string
  started_at: number
  uptime_s: number
  tasks: {
    total: number
    by_status: Record<string, number>
    active: { task_id: string; status: string; stage: string | null }[]
  }
  events_total: number
  db: { path: string; size_bytes: number }
  matlab_mcp: { initialized: boolean; started: boolean; session_alive: boolean; loop_alive: boolean }
  llm: { configured: boolean; base_url_host?: string; default_model?: string; planner_model?: string | null }
}

// SSE event types
export type SseEvent =
  | { type: 'stage'; stage: string; label: string; ts?: number }
  | {
      type: 'node'
      stage: string
      node?: string
      phase?: 'start' | 'done'
      ts?: number
      // 透明化载荷（M0）：节点完成时刻外发的产物，按 node 类型出现
      plan?: Record<string, unknown>
      code?: string
      code_paths?: string[]
      tool_result?: ToolResult
      metrics?: Record<string, unknown>
      retries?: Record<string, number>
      verdict?: Verdict
      knowledge_ref?: string
      criteria_count?: number
      [k: string]: unknown
    }
  | {
      type: 'knowledge_done'
      criteria_count: number
      criteria?: CriteriaItem[]
      knowledge?: KnowledgeSummary
      ts?: number
    }
  | { type: 'interrupt'; stage: string; label: string; payload: InterruptPayload; ts?: number }
  | { type: 'resume'; label: string; approved: boolean; ts?: number }
  | { type: 'llm_call'; label: string; role?: string; model?: string; ts?: number }
  | {
      type: 'llm_usage'
      label: string
      role?: string
      model?: string
      prompt_tokens?: number | null
      completion_tokens?: number | null
      total_tokens?: number | null
      duration_s?: number | null
      ts?: number
    }
  | { type: 'done'; status: string; result: TaskResult | null; ts?: number }
  | { type: 'error'; error: string; error_class?: string; ts?: number }
  | { type: 'heartbeat'; ts?: number }
  | { type: 'unknown'; ts?: number; [k: string]: unknown }

