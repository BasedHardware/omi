// The one place that knows how to get OpenClaw / Hermes / Codex onto a
// machine. Used to live only inside AgentsTab (renderer) — main's chat-path
// "you're not connected" message went through adapterActivationError, which
// had no idea Settings already knew the real install command, so it could
// only point at Settings rather than just saying `npm install -g openclaw`.
// Same data, one owner, both places read it.

import type { CodingAgentId } from './types'

export type ExternalAgentId = Exclude<CodingAgentId, 'acp'>

export type AgentGuide = {
  description: string
  /** Real shell commands to install the CLI (empty when there's no one-liner). */
  installCommands: string[]
  /** Prose install pointer when there's no install command (e.g. Hermes). */
  installNote?: string
  /** Suggested launch command the Connect button auto-fills + saves. */
  suggestedCommand: string
  docsUrl: string
  /** How to sign in after install (honest — Omi does not automate these logins). */
  authNote: string
  /** Codex exposes an in-app OpenAI API-key lane; the others don't (yet). */
  supportsApiKey?: boolean
}

export const EXTERNAL_AGENT_GUIDES: Record<ExternalAgentId, AgentGuide> = {
  openclaw: {
    description: 'Open-source AI coding assistant with its own gateway and model routing.',
    installCommands: ['npm install -g openclaw@latest'],
    suggestedCommand: 'openclaw acp',
    docsUrl: 'https://docs.openclaw.ai/install',
    authNote: 'After installing, sign in: run `openclaw onboard` in a terminal.'
  },
  hermes: {
    description: "Nous Research's Hermes agent, connected over its ACP server mode.",
    installCommands: [],
    installNote: 'Install the Hermes CLI from its documentation.',
    suggestedCommand: 'hermes acp',
    docsUrl: 'https://hermes-agent.nousresearch.com/docs',
    authNote: 'After installing, sign in: run `hermes login` in a terminal.'
  },
  codex: {
    description: "OpenAI's Codex agent, driven through the official codex-acp bridge.",
    installCommands: ['npm install -g @openai/codex'],
    suggestedCommand: 'npx -y @agentclientprotocol/codex-acp',
    docsUrl: 'https://github.com/agentclientprotocol/codex-acp',
    authNote: 'Sign in with `codex login`, or add your OpenAI API key below.',
    supportsApiKey: true
  }
}

export function isExternalAgentId(id: CodingAgentId): id is ExternalAgentId {
  return id !== 'acp'
}
