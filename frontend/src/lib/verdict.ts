// frontend/src/lib/verdict.ts
// 最终验收结算的取数逻辑。逐条裁决（metric/expected/actual/passed/reason/hardcoded）
// 由 verify 节点在结算时随 node done 事件发出：live 观看时在事件流里，恢复历史任务时
// 事件流不重放，经 /tasks/{id}/events 回放端点补拉。两边共用本提取函数。
import type { SseEvent, VerdictCriterionResult } from '@/types'

export interface FinalVerdict {
  summary: string | null
  rows: VerdictCriterionResult[]
}

export function extractFinalVerdict(events: SseEvent[]): FinalVerdict | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]
    if (e?.type !== 'node' || e.node !== 'verify' || e.phase !== 'done') continue
    const results = e.verdict?.results
    if (Array.isArray(results) && results.length > 0) {
      return { summary: e.verdict?.summary ?? null, rows: results }
    }
  }
  return null
}
