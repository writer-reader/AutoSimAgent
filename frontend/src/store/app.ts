// frontend/src/store/app.ts
import { create } from 'zustand'
import { api } from '@/api/client'
import type { SseEvent, CriteriaItem, InterruptPayload, TaskResult, TaskListItem } from '@/types'

const SESSION_KEY = 'control_agent_task_id'

export interface LogEntry {
  event: SseEvent
  id: number
}

interface AppState {
  step: 1 | 2 | 3

  // Step 1
  paperId: string | null
  pdfPath: string | null
  importError: string | null
  startError: string | null

  // Step 2
  taskId: string | null
  taskStatus: string | null
  currentStage: string | null
  currentStageLabel: string | null
  knownStages: string[]
  eventLog: LogEntry[]
  sseDisconnected: boolean
  // SSE 断点续传游标（事件 seq）+ 手动重连计数器
  lastSeq: number
  streamNonce: number

  // 任务历史（侧栏）
  taskHistory: TaskListItem[]

  // approval
  approvalPayload: InterruptPayload | null
  approvalCount: number
  currentInterruptKey: string | null

  // Step 3
  finalResult: TaskResult | null
  criteria: CriteriaItem[]
  step2Error: string | null
}

interface AppActions {
  setStep: (s: 1 | 2 | 3) => void
  setPaperInfo: (paperId: string, pdfPath: string) => void
  setImportError: (e: string | null) => void
  setStartError: (e: string | null) => void
  setTaskId: (id: string) => void
  setTaskStatus: (s: string) => void
  clearTask: () => void
  startNewTask: () => void
  appendEvent: (ev: SseEvent) => void
  setApproval: (payload: InterruptPayload) => void
  clearApproval: () => void
  setCriteria: (items: CriteriaItem[]) => void
  setFinalResult: (result: TaskResult | null, status: string) => void
  setSseDisconnected: (v: boolean) => void
  setStep2Error: (e: string) => void
  clearStep2Error: () => void
  addKnownStage: (stage: string) => void
  setLastSeq: (n: number) => void
  incStreamNonce: () => void
  loadTaskHistory: () => Promise<void>
  selectTask: (id: string) => Promise<void>
}

const STAGE_ORDER = [
  'mineru', 'adapter', 'knowledge', 'graph:init', 'graph:plan',
  'request_approval', 'resuming', 'done',
]

let logCounter = 0

export const useAppStore = create<AppState & AppActions>((set, get) => ({
  step: 1,
  paperId: null,
  pdfPath: null,
  importError: null,
  startError: null,
  taskId: null,
  taskStatus: null,
  currentStage: null,
  currentStageLabel: null,
  knownStages: [...STAGE_ORDER],
  eventLog: [],
  sseDisconnected: false,
  lastSeq: 0,
  streamNonce: 0,
  taskHistory: [],
  approvalPayload: null,
  approvalCount: 0,
  currentInterruptKey: null,
  finalResult: null,
  criteria: [],
  step2Error: null,

  setStep: (s) => set({ step: s }),

  setPaperInfo: (paperId, pdfPath) =>
    set({ paperId, pdfPath, importError: null, startError: null }),

  setImportError: (e) => set({ importError: e }),
  setStartError: (e) => set({ startError: e }),

  setTaskId: (id) => {
    sessionStorage.setItem(SESSION_KEY, id)
    set({ taskId: id })
  },

  setTaskStatus: (s) => set({ taskStatus: s }),

  clearTask: () => {
    sessionStorage.removeItem(SESSION_KEY)
    set({
      taskId: null, taskStatus: null, currentStage: null, currentStageLabel: null,
      eventLog: [], sseDisconnected: false, approvalPayload: null, approvalCount: 0,
      currentInterruptKey: null, finalResult: null, step2Error: null,
      criteria: [], knownStages: [...STAGE_ORDER], lastSeq: 0, streamNonce: 0,
    })
  },

  // 一键新建任务：清当前任务 + 清 Step1 残留，回到导入页（header/侧栏/结果页共用）
  startNewTask: () => {
    get().clearTask()
    set({ step: 1, paperId: null, pdfPath: null, importError: null, startError: null })
  },

  appendEvent: (ev) => {
    set(s => {
      const entry: LogEntry = { event: ev, id: logCounter++ }
      const log = [...s.eventLog, entry].slice(-200)
      let stage = s.currentStage
      let label = s.currentStageLabel
      if (ev.type === 'stage') { stage = ev.stage; label = ev.label }
      return { eventLog: log, currentStage: stage, currentStageLabel: label }
    })
  },

  addKnownStage: (stage) => {
    set(s => {
      if (s.knownStages.includes(stage)) return s
      return { knownStages: [...s.knownStages, stage] }
    })
  },

  setApproval: (payload) =>
    set(s => ({
      approvalPayload: payload,
      approvalCount: s.approvalCount + 1,
      currentInterruptKey: payload.interrupt_key,
    })),

  clearApproval: () =>
    set({ approvalPayload: null, currentInterruptKey: null }),

  setCriteria: (items) => set({ criteria: items }),

  setFinalResult: (result, status) =>
    set({ finalResult: result, taskStatus: status }),

  setSseDisconnected: (v) => set({ sseDisconnected: v }),

  setLastSeq: (n) => set(s => (n > s.lastSeq ? { lastSeq: n } : s)),

  incStreamNonce: () => set(s => ({ streamNonce: s.streamNonce + 1 })),

  // 拉取任务历史（侧栏展示，时间倒序）
  loadTaskHistory: async () => {
    try {
      const resp = await api.taskList({ limit: 50 })
      set({ taskHistory: resp.items })
    } catch {
      // 拉取失败不打断主流程，侧栏显示空态
    }
  },

  // 选择历史任务：重置流状态 → 恢复 taskId → 按 status 落到对应步骤
  selectTask: async (id) => {
    try {
      const task = await api.taskStatus(id)
      set({
        eventLog: [], lastSeq: 0, streamNonce: 0,
        approvalPayload: null, currentInterruptKey: null,
        step2Error: null, sseDisconnected: false,
        currentStage: null, currentStageLabel: null,
        knownStages: [...STAGE_ORDER], finalResult: null, criteria: [],
      })
      sessionStorage.setItem(SESSION_KEY, id)
      set({ taskId: task.task_id, taskStatus: task.status })
      if (task.status === 'completed' && task.result) {
        // 恢复已完成任务：验收标准从任务记录带过来（事件流不重放）
        const crits = (task.criteria ?? []).map(c => ({
          criteria_id: c.criterion_id,
          description: c.description || c.metric || c.criterion_id,
        }))
        set({ finalResult: task.result, taskStatus: 'completed', step: 3, criteria: crits })
      } else {
        if (task.error) set({ step2Error: task.error, taskStatus: 'failed' })
        set({ step: 2 })
      }
    } catch {
      // 任务不存在（已被清理）：静默忽略
    }
  },

  setStep2Error: (e) => set({ step2Error: e, taskStatus: 'failed' }),

  // 只清错误标记，不动 taskStatus（重连回放发现任务已被 restart/resume 时用）
  clearStep2Error: () => set({ step2Error: null }),
}))

export const SESSION_TASK_KEY = SESSION_KEY
