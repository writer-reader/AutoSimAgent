import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from './app'

beforeEach(() => {
  useAppStore.setState({
    step: 1,
    taskId: null,
    approvalPayload: null,
    approvalCount: 0,
    currentInterruptKey: null,
    eventLog: [],
    criteria: [],
    step2Error: null,
    finalResult: null,
    knownStages: ['mineru', 'adapter', 'knowledge', 'done'],
  })
  sessionStorage.clear()
})

describe('setTaskId', () => {
  it('writes to store', () => {
    useAppStore.getState().setTaskId('task_abc123')
    expect(useAppStore.getState().taskId).toBe('task_abc123')
  })
})

describe('clearTask', () => {
  it('clears task state from store', () => {
    useAppStore.getState().setTaskId('task_abc123')
    useAppStore.getState().clearTask()
    expect(useAppStore.getState().taskId).toBeNull()
    expect(useAppStore.getState().finalResult).toBeNull()
    expect(useAppStore.getState().criteria).toEqual([])
  })
})

describe('setApproval', () => {
  it('increments approvalCount and stores interrupt_key', () => {
    const payload = { tool: 'run_code', language: 'matlab', code: 'x=1', interrupt_key: 'key_1' }
    useAppStore.getState().setApproval(payload)
    expect(useAppStore.getState().approvalCount).toBe(1)
    expect(useAppStore.getState().currentInterruptKey).toBe('key_1')

    const payload2 = { ...payload, interrupt_key: 'key_2' }
    useAppStore.getState().setApproval(payload2)
    expect(useAppStore.getState().approvalCount).toBe(2)
    expect(useAppStore.getState().currentInterruptKey).toBe('key_2')
  })
})

describe('addKnownStage', () => {
  it('appends unknown stage, skips duplicates', () => {
    useAppStore.getState().addKnownStage('graph:verify')
    const stages = useAppStore.getState().knownStages
    expect(stages).toContain('graph:verify')
    const prevLen = stages.length
    useAppStore.getState().addKnownStage('graph:verify')
    expect(useAppStore.getState().knownStages.length).toBe(prevLen)
  })
})

describe('appendEvent (log cap)', () => {
  it('keeps at most 200 entries', () => {
    for (let i = 0; i < 210; i++) {
      useAppStore.getState().appendEvent({ type: 'stage', stage: `s${i}`, label: `l${i}` })
    }
    expect(useAppStore.getState().eventLog.length).toBe(200)
  })
})
