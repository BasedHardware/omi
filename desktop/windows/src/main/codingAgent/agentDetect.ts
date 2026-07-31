// PATH auto-detection for the external coding-agent CLIs (Codex / Hermes /
// OpenClaw). Settings → Agents calls this so it can show "Installed ✓ v1.2.3"
// instead of asking the user to guess whether they've installed the tool and
// paste a launch command. This detects the AGENT's own CLI binary — the thing
// the user installs (`npm install -g @openai/codex`, etc.) and logs in to. The
// Codex ACP *bridge* is still fetched via npx at launch (see the suggested
// command), but `codex` on PATH is the honest "is it installed" signal.
//
// A shell is used deliberately: on Windows an npm-global CLI is a `.cmd` shim
// that only runs through a shell, and `where` / `command -v` are shell builtins.
// The binary names are hardcoded constants (never user input) AND `detectAgentCli`
// rejects anything outside a strict `[A-Za-z0-9._-]` charset before it reaches the
// shell, so the command strings can carry no injectable input. Version probing is
// best-effort and never fails detection.

import { exec } from 'child_process'
import type { AgentCliDetection, AgentDetectionMap, CodingAgentId } from '../../shared/types'

export type { AgentCliDetection } from '../../shared/types'

/** The three external coding-agent CLIs (Claude Code is built in; pi-mono is the
 *  managed-cloud chat engine, neither is a user-installed binary). */
type ExternalCodingAgentId = Exclude<CodingAgentId, 'acp'>

/** The CLI binary probed on PATH for each external agent. */
const AGENT_CLI_BINARY: Record<ExternalCodingAgentId, string> = {
  codex: 'codex',
  hermes: 'hermes',
  openclaw: 'openclaw'
}

/** Injectable command runner so detection is unit-testable without a shell. */
export type CommandRunner = (
  command: string
) => Promise<{ code: number; stdout: string; stderr: string }>

const DEFAULT_TIMEOUT_MS = 5000

const defaultRunner: CommandRunner = (command) =>
  new Promise((resolve) => {
    exec(command, { timeout: DEFAULT_TIMEOUT_MS, windowsHide: true }, (error, stdout, stderr) => {
      // exec's error.code is the process exit code on a non-zero exit, or a
      // string errno (e.g. 'ENOENT') when the shell itself couldn't run. Either
      // way a non-zero/failed run means "not found here".
      const code =
        error && typeof (error as { code?: unknown }).code === 'number'
          ? (error as { code: number }).code
          : error
            ? 1
            : 0
      resolve({ code, stdout: stdout?.toString() ?? '', stderr: stderr?.toString() ?? '' })
    })
  })

/** Pull a semver-ish token out of a `--version` line, else the trimmed line. */
export function parseVersion(line: string): string | undefined {
  const trimmed = line.trim()
  if (!trimmed) return undefined
  const semver = trimmed.match(/\d+\.\d+\.\d+[^\s]*/)
  if (semver) return semver[0]
  // Fall back to the whole first line, bounded so a chatty CLI can't flood the UI.
  return trimmed.slice(0, 40)
}

/** Binary names safe to interpolate into a shell string — the detector only ever
 *  probes hardcoded CLI names, so anything else is a programming error / hostile
 *  input and must never reach the shell. */
const SAFE_BINARY = /^[A-Za-z0-9._-]+$/

/** Locate + version-probe a single binary. Never throws. */
export async function detectAgentCli(
  binary: string,
  run: CommandRunner = defaultRunner
): Promise<AgentCliDetection> {
  // Injection guard: refuse to build a shell command from an unexpected name.
  if (!SAFE_BINARY.test(binary)) return { installed: false }
  const locate = process.platform === 'win32' ? `where ${binary}` : `command -v ${binary}`
  const located = await run(locate).catch(() => ({ code: 1, stdout: '', stderr: '' }))
  if (located.code !== 0) return { installed: false }

  const path = located.stdout
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)[0]

  let version: string | undefined
  try {
    const probed = await run(`${binary} --version`)
    if (probed.code === 0) {
      version = parseVersion(probed.stdout.split(/\r?\n/)[0] ?? '')
    }
  } catch {
    /* version is best-effort — a missing/hanging --version never un-installs it */
  }

  return { installed: true, path, version }
}

/** Detect every external agent CLI in parallel. */
export async function detectAgents(run: CommandRunner = defaultRunner): Promise<AgentDetectionMap> {
  const ids = Object.keys(AGENT_CLI_BINARY) as ExternalCodingAgentId[]
  const entries = await Promise.all(
    ids.map(async (id) => [id, await detectAgentCli(AGENT_CLI_BINARY[id], run)] as const)
  )
  return Object.fromEntries(entries) as AgentDetectionMap
}
