import { useEffect, useState } from 'react'
import { auth } from './firebase'
import { getPreferences } from './preferences'
import { looksLikeAction, planActions } from './actionPlanner'
import { callAgentLLM } from './agentLLM'
import type { ChatMessage, PiChatToolCall } from '../../../shared/types'

export type TaskAgentProvider = 'pi' | 'claude-acp'
export type TaskAgentStatus = 'queued' | 'running' | 'waiting-approval' | 'completed' | 'failed'

export type TaskAgentRun = {
  id: string
  prompt: string
  provider: TaskAgentProvider
  status: TaskAgentStatus
  createdAt: number
  updatedAt: number
  result?: string
  error?: string
  toolCalls: PiChatToolCall[]
  events: string[]
}

type StartRequest = {
  prompt: string
  provider: TaskAgentProvider
}

const runs: TaskAgentRun[] = []
const listeners = new Set<() => void>()

function emit(): void {
  listeners.forEach((listener) => listener())
}

function snapshot(): TaskAgentRun[] {
  return [...runs].sort((a, b) => b.createdAt - a.createdAt)
}

function updateRun(id: string, patch: Partial<TaskAgentRun>): void {
  const run = runs.find((item) => item.id === id)
  if (!run) return
  Object.assign(run, patch, { updatedAt: Date.now() })
  emit()
}

function addEvent(id: string, event: string): void {
  const run = runs.find((item) => item.id === id)
  if (!run) return
  run.events = [...run.events, event]
  run.updatedAt = Date.now()
  emit()
}

async function maybeRunAutomation(id: string, prompt: string): Promise<boolean> {
  if (!looksLikeAction(prompt)) return false
  if (!window.omi.automationEnabled || !getPreferences().automationConsentedAt) {
    throw new Error('UI automation needs the Privacy setting enabled before an agent task can act.')
  }
  addEvent(id, 'Planning UI action')
  const handle = await window.omi.automationTargetWindow().catch(() => null)
  const result = await planActions(prompt, {
    getSnapshot: () => window.omi.automationSnapshot(handle ?? undefined),
    callLLM: callAgentLLM
  })
  if (!result.ok) {
    if (result.kind === 'chat') return false
    throw new Error(`Could not build a safe UI plan: ${result.reason}`)
  }
  updateRun(id, { status: 'waiting-approval' })
  addEvent(id, 'Waiting for native approval')
  const approval = await window.omi.automationConfirmRun(result.plan)
  if (approval.canceled) {
    throw new Error('User canceled the UI action.')
  }
  if (!approval.ok) {
    throw new Error(approval.message ?? 'UI action failed.')
  }
  updateRun(id, {
    status: 'completed',
    result: 'Completed approved UI action.'
  })
  addEvent(id, 'Approved UI action completed')
  return true
}

async function runWithProvider(run: TaskAgentRun): Promise<void> {
  const messages: ChatMessage[] = [{ role: 'user', content: run.prompt }]
  switch (run.provider) {
    case 'pi': {
      if (!window.omi.piChatEnabled) throw new Error('Pi/Omi chat is not enabled in this build.')
      const token = await auth.currentUser?.getIdToken()
      const response = await window.omi.piChatSend({ token: token ?? '', messages })
      updateRun(run.id, {
        status: 'completed',
        result: response.text,
        toolCalls: response.toolCalls
      })
      addEvent(run.id, `${response.toolCalls.length} local tool call(s)`)
      return
    }
    case 'claude-acp': {
      const response = await window.omi.claudeAcpChatSend({ messages })
      updateRun(run.id, { status: 'completed', result: response.text })
      return
    }
  }
}

async function executeRun(run: TaskAgentRun): Promise<void> {
  updateRun(run.id, { status: 'running' })
  addEvent(run.id, `Started with ${run.provider === 'pi' ? 'Pi/Omi' : 'Claude account'}`)
  try {
    const handledByAutomation = await maybeRunAutomation(run.id, run.prompt)
    if (!handledByAutomation) await runWithProvider(run)
  } catch (e) {
    updateRun(run.id, {
      status: 'failed',
      error: (e as Error).message
    })
  }
}

export function enqueueTaskAgentRun(request: StartRequest): TaskAgentRun {
  const prompt = request.prompt.trim()
  if (!prompt) throw new Error('Task prompt is required')
  const now = Date.now()
  const run: TaskAgentRun = {
    id: `agent-task-${crypto.randomUUID()}`,
    prompt,
    provider: request.provider,
    status: 'queued',
    createdAt: now,
    updatedAt: now,
    toolCalls: [],
    events: []
  }
  runs.unshift(run)
  emit()
  void executeRun(run)
  return run
}

export function subscribeTaskAgentRuns(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getTaskAgentRunsSnapshot(): TaskAgentRun[] {
  return snapshot()
}

export function useTaskAgentRuns(): TaskAgentRun[] {
  const [value, setValue] = useState<TaskAgentRun[]>(() => getTaskAgentRunsSnapshot())
  useEffect(() => subscribeTaskAgentRuns(() => setValue(getTaskAgentRunsSnapshot())), [])
  return value
}
