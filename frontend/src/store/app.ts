// frontend/src/store/app.ts
import { create } from 'zustand'
import { api } from '@/api/client'
import { extractFinalVerdict, type FinalVerdict } from '@/lib/verdict'
import type { SseEvent, CriteriaItem, InterruptPayload, TaskResult, TaskListItem, TaskStatusResponse } from '@/types'

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
  // 最终验收结算（逐条 expected/actual/reason）：live 路径从事件流取，恢复路径从事件回放端点补拉
  finalVerdict: FinalVerdict | null
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
  loadTaskById: (id: string, signal?: AbortSignal) => Promise<void>
  restoreSettled: (task: TaskStatusResponse) => void
  fetchFinalVerdict: (id: string) => Promise<void>
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
  finalVerdict: null,
  step2Error: null,

  setStep: (s) => set({ step: s }),

  setPaperInfo: (paperId, pdfPath) =>
    set({ paperId, pdfPath, importError: null, startError: null }),

  setImportError: (e) => set({ importError: e }),
  setStartError: (e) => set({ startError: e }),

  setTaskId: (id) => {
    set({ taskId: id })
  },

  setTaskStatus: (s) => set({ taskStatus: s }),

  clearTask: () => {
    set({
      taskId: null, taskStatus: null, currentStage: null, currentStageLabel: null,
      eventLog: [], sseDisconnected: false, approvalPayload: null, approvalCount: 0,
      currentInterruptKey: null, finalResult: null, step2Error: null,
      criteria: [], finalVerdict: null, knownStages: [...STAGE_ORDER], lastSeq: 0, streamNonce: 0,
    })
  },

  // 一键新建任务：清当前任务 + 清 Step1 残留，回到导入页（唯一入口：任务记录侧栏）
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

  // 按 URL 参数加载任务详情（路由为唯一事实来源；已在 store 中的活动任务由调用方跳过）。
  // signal 中止（组件卸载/参数变更）时不再写 store，避免已删除/已离开的任务复活到界面上。
  loadTaskById: async (id, signal) => {
    try {
      const task = await api.taskStatus(id)
      if (signal?.aborted) return
      set({
        eventLog: [], lastSeq: 0, streamNonce: 0,
        approvalPayload: null, currentInterruptKey: null,
        step2Error: null, sseDisconnected: false,
        currentStage: null, currentStageLabel: null,
        knownStages: [...STAGE_ORDER], finalResult: null, criteria: [], finalVerdict: null,
      })
      if (task.result) {
        // 已结算（completed / failed 都可能带 result）：与 live done 路径同语义，直达结果页
        get().restoreSettled(task)
      } else {
        set({ taskId: task.task_id, taskStatus: task.status })
        if (task.error) set({ step2Error: task.error, taskStatus: 'failed' })
        set({ step: 2 })
      }
    } catch {
      if (signal?.aborted) return
      // 任务不存在（已被清理）：TaskDetailPage 呈现未找到态
      throw new Error('task_not_found')
    }
  },

  // 已结算任务恢复（URL 直达共用）：result + 验收标准 + 补拉最终验收结算
  restoreSettled: (task) => {
    const crits = (task.criteria ?? []).map(c => ({
      criteria_id: c.criterion_id,
      description: c.description || c.metric || c.criterion_id,
    }))
    set({
      taskId: task.task_id, taskStatus: task.status, step: 3,
      finalResult: task.result, criteria: crits,
    })
    void get().fetchFinalVerdict(task.task_id)
  },

  fetchFinalVerdict: async (id) => {
    try {
      const resp = await api.taskEvents(id)
      const evs = resp.events.map(e => e.data)
      // 事件归档进 eventLog：结果页的统计条/过程记录在恢复路径下与 live 路径同源（真实数字）。
      // 单次 set，避免逐条 append 造成 195 次重渲染。
      const lastStage = [...evs].reverse().find(e => e.type === 'stage')
      set(s => ({
        eventLog: evs.map(ev => ({ event: ev, id: logCounter++ })).slice(-200),
        lastSeq: Math.max(s.lastSeq, resp.events.length ? resp.events[resp.events.length - 1]!.seq : 0),
        currentStage: lastStage?.stage ?? s.currentStage,
        currentStageLabel: lastStage?.label ?? s.currentStageLabel,
      }))
      const verdict = extractFinalVerdict(evs)
      if (verdict) set({ finalVerdict: verdict })
    } catch {
      // 明细补拉失败不阻断结果页，回落到验收标准列表
    }
  },

  setStep2Error: (e) => set({ step2Error: e, taskStatus: 'failed' }),

  // 只清错误标记，不动 taskStatus（重连回放发现任务已被 restart/resume 时用）
  clearStep2Error: () => set({ step2Error: null }),
}))

