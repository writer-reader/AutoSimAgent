// frontend/src/store/app.ts
import { create } from 'zustand'
import type { SseEvent, CriteriaItem, InterruptPayload, TaskResult } from '@/types'

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
  clearTask: () => void
  appendEvent: (ev: SseEvent) => void
  setApproval: (payload: InterruptPayload) => void
  clearApproval: () => void
  setCriteria: (items: CriteriaItem[]) => void
  setFinalResult: (result: TaskResult, status: string) => void
  setSseDisconnected: (v: boolean) => void
  setStep2Error: (e: string) => void
  addKnownStage: (stage: string) => void
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

  clearTask: () => {
    sessionStorage.removeItem(SESSION_KEY)
    set({
      taskId: null, taskStatus: null, currentStage: null, currentStageLabel: null,
      eventLog: [], sseDisconnected: false, approvalPayload: null, approvalCount: 0,
      currentInterruptKey: null, finalResult: null, step2Error: null,
      knownStages: [...STAGE_ORDER],
    })
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

  setStep2Error: (e) => set({ step2Error: e, taskStatus: 'failed' }),
}))

export const SESSION_TASK_KEY = SESSION_KEY
