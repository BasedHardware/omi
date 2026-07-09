// Settings → Agents: connect the coding agents Omi can delegate tasks to.
// Claude Code ships built in; OpenClaw, Hermes, and Codex are external CLIs
// the user installs and points Omi at with a launch command. "Test" spawns the
// agent and completes a real ACP handshake, so a green check means the command
// actually works — not just that a string was saved.

import { useEffect, useState } from 'react'
import { Bot, Terminal } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import type { CodingAgentId, CodingAgentInfo } from '../../../../../shared/types'

type ExternalAgentId = Exclude<CodingAgentId, 'acp'>

type AgentGuide = {
  description: string
  /** Shell steps to install the agent itself (shown as copyable lines). */
  installSteps: string[]
  /** Suggested launch command for the command field. */
  suggestedCommand: string
  docsUrl: string
}

const EXTERNAL_AGENT_GUIDES: Record<ExternalAgentId, AgentGuide> = {
  openclaw: {
    description: 'Open-source AI coding assistant with its own gateway and model routing.',
    installSteps: ['npm install -g openclaw@latest', 'openclaw onboard'],
    suggestedCommand: 'openclaw acp',
    docsUrl: 'https://docs.openclaw.ai/install'
  },
  hermes: {
    description: "Nous Research's Hermes agent, connected over its ACP server mode.",
    installSteps: ['Install the Hermes CLI (see docs)', 'hermes login'],
    suggestedCommand: 'hermes acp',
    docsUrl: 'https://hermes-agent.nousresearch.com/docs'
  },
  codex: {
    description: "OpenAI's Codex agent, driven through the official codex-acp bridge.",
    installSteps: ['npm install -g @openai/codex', 'codex login'],
    suggestedCommand: 'npx @agentclientprotocol/codex-acp',
    docsUrl: 'https://github.com/zed-industries/codex-acp'
  }
}

type TestState = { running: boolean; verdict?: 'ok' | 'failed'; detail?: string }

export function AgentsTab(): React.JSX.Element {
  const [agents, setAgents] = useState<CodingAgentInfo[]>([])
  const [commands, setCommands] = useState<Partial<Record<ExternalAgentId, string>>>(
    () => getPreferences().agentCommands ?? {}
  )
  const [tests, setTests] = useState<Partial<Record<CodingAgentId, TestState>>>({})

  const refresh = (): void => {
    void window.omi
      .codingAgentList(getPreferences().agentCommands)
      .then(setAgents)
      .catch(() => setAgents([]))
  }

  useEffect(refresh, [])

  const saveCommand = (id: ExternalAgentId): void => {
    const trimmed = commands[id]?.trim()
    const next = { ...(getPreferences().agentCommands ?? {}) }
    if (trimmed) next[id] = trimmed
    else delete next[id]
    setPreferences({ agentCommands: next })
    setTests((t) => ({ ...t, [id]: {} }))
    refresh()
  }

  const runTest = (id: CodingAgentId): void => {
    setTests((t) => ({ ...t, [id]: { running: true } }))
    void window.omi
      .codingAgentTest(id, getPreferences().agentCommands)
      .then((r) =>
        setTests((t) => ({
          ...t,
          [id]: { running: false, verdict: r.ok ? 'ok' : 'failed', detail: r.error }
        }))
      )
      .catch((e: Error) =>
        setTests((t) => ({ ...t, [id]: { running: false, verdict: 'failed', detail: e.message } }))
      )
  }

  const testLine = (id: CodingAgentId): React.JSX.Element | null => {
    const state = tests[id]
    if (!state?.verdict) return null
    return state.verdict === 'ok' ? (
      <div className="mt-2 text-sm text-emerald-400">
        Connected — the agent answered the handshake.
      </div>
    ) : (
      <div className="mt-2 text-sm text-amber-400">
        {state.detail ?? "Couldn't reach the agent."}
      </div>
    )
  }

  const claudeCode = agents.find((a) => a.id === 'acp')

  return (
    <div>
      <p className="mb-2 text-sm text-text-tertiary">
        Ask for an agent by name in chat or push-to-talk — “ask Codex to fix the failing test”, “use
        Claude Code to add a readme” — and Omi hands the task over, streaming the agent’s progress
        into the conversation. If the agent you named is down, Omi falls back to the next connected
        one.
      </p>

      <SettingRow
        icon={Bot}
        title="Claude Code"
        subtitle="Built in — no install needed. Signs in with your Claude account."
        keywords="claude code anthropic coding agent builtin"
        dot={claudeCode?.connected ? 'on' : 'off'}
        control={
          <button
            onClick={() => runTest('acp')}
            disabled={tests.acp?.running}
            className="btn-ghost disabled:opacity-40"
          >
            {tests.acp?.running ? 'Testing…' : 'Test'}
          </button>
        }
      >
        {testLine('acp')}
      </SettingRow>

      {(Object.keys(EXTERNAL_AGENT_GUIDES) as ExternalAgentId[]).map((id) => {
        const guide = EXTERNAL_AGENT_GUIDES[id]
        const info = agents.find((a) => a.id === id)
        const displayName = info?.displayName ?? id
        const connected = info?.connected ?? false
        return (
          <SettingRow
            key={id}
            icon={Terminal}
            title={displayName}
            subtitle={guide.description}
            keywords={`${id} coding agent acp command connect install`}
            dot={connected ? 'on' : 'off'}
            control={
              connected ? (
                <button
                  onClick={() => runTest(id)}
                  disabled={tests[id]?.running}
                  className="btn-ghost disabled:opacity-40"
                >
                  {tests[id]?.running ? 'Testing…' : 'Test'}
                </button>
              ) : (
                <span className="text-sm text-text-tertiary">Not connected</span>
              )
            }
          >
            {!connected && (
              <div className="mb-3 rounded-lg bg-white/[0.04] p-3 text-sm text-text-tertiary">
                <div className="mb-1 font-medium text-text-secondary">Install {displayName}</div>
                {guide.installSteps.map((step) => (
                  <code key={step} className="mb-1 block font-mono text-xs text-text-secondary">
                    {step}
                  </code>
                ))}
                <a
                  href={guide.docsUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs underline"
                >
                  Setup guide
                </a>
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                value={commands[id] ?? ''}
                onChange={(e) => setCommands((c) => ({ ...c, [id]: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    saveCommand(id)
                  }
                }}
                placeholder={`Launch command, e.g. ${guide.suggestedCommand}`}
                className="glass-subtle w-full rounded-lg px-4 py-3 font-mono text-sm text-text-secondary focus:outline-none"
                spellCheck={false}
              />
              <button onClick={() => saveCommand(id)} className="btn-ghost shrink-0">
                Save
              </button>
            </div>
            {testLine(id)}
          </SettingRow>
        )
      })}
    </div>
  )
}
