// IPC surface for the realtime-hub TOOL LOOP (INV-AGENT). The default hub-native
// voice path can now ACT, not just talk: a spoken request dispatches Omi tools
// through the SAME in-process host executor registry the typed chat path uses
// (`executeHostTool`), mirroring macOS' `hubDidRequestTool` in-process dispatch —
// NOT a second executor path and NOT the pi socket relay.
//
//   * `voiceHub:toolCatalog` returns the provider-neutral tool declarations the warm
//     session advertises. Built HOST-side from the shared manifest with a
//     host-derived execution role (read from the main_chat surface session, never
//     model/renderer-claimed), so a leaf voice session is never handed coordinator
//     tools (spawn_agent, run_agent_and_wait, …).
//   * `voiceHub:execute` (exposed as `voiceToolExecute`) runs one requested tool and
//     returns its result string. Control tools → `handleAgentControlToolCall` with a
//     `trustedUserControl:false` context; product tools → the serviceable registry;
//     `spawn_agent` → the kernel delegation door — all inside `executeHostTool`.
//
// AUTHORITY (INV-AGENT). Authority is HOST-derived from the main_chat surface
// session (a trusted, top-level, coordinator-equivalent user surface), never from
// the model or the renderer. This is the OPPOSITE of the renderer's trusted-direct
// `agentControlCall` door: voice tool calls are model-authority and can NEVER be
// trusted user control. Both handlers refuse while the owner is the shared
// DEFAULT_LOCAL_OWNER_ID (not signed in / auth relay not arrived) — Mac's
// `currentOwnerId()` throws in the same state.

import { ipcMain } from 'electron'
import {
  controlPlaneOwnerId,
  getAgentRuntimeKernel,
  hasKnownControlPlaneOwner
} from '../agentKernel/controlPlane'
import { isAgentControlToolName } from '../agentKernel/controlTools'
import { executeHostTool, WINDOWS_SERVICEABLE_PRODUCT_TOOLS } from '../agentKernel/toolRelayBridge'
import { isToolAvailableForContext, omiToolManifest } from '../agentKernel/omiToolManifest'
import type { AgentRuntimeKernel } from '../agentKernel/kernel'
import type { SurfaceRef } from '../agentKernel/surfaceSession'
import type { VoiceToolDeclaration, VoiceToolExecuteArgs } from '../../shared/types'

/** Voice tools resolve against the SAME main_chat surface session typed chat uses
 *  (so spawn_agent runs and the transcript stay one thread), pinned to pi-mono. */
const MAIN_CHAT_ADAPTER_ID = 'pi-mono'

/** What the handlers need from the host. Defaulted to the process-wide kernel and
 *  the main-side authoritative owner; injected in tests. */
export interface VoiceToolDeps {
  kernel: AgentRuntimeKernel
  ownerId: string
  ownerReady: boolean
}

function defaultDeps(): VoiceToolDeps {
  return {
    kernel: getAgentRuntimeKernel(),
    ownerId: controlPlaneOwnerId(),
    ownerReady: hasKnownControlPlaneOwner()
  }
}

function mainChatSurfaceRef(): SurfaceRef {
  return { surfaceKind: 'main_chat', externalRefKind: 'chat', externalRefId: 'default' }
}

/** Resolve (creating if needed) the main_chat surface session id the voice thread
 *  acts under. Idempotent — the same session typed chat and the transcript use. */
function mainChatSessionId(deps: VoiceToolDeps): string {
  return deps.kernel.resolveSurfaceSession({
    ownerId: deps.ownerId,
    surfaceRef: mainChatSurfaceRef(),
    defaultAdapterId: MAIN_CHAT_ADAPTER_ID
  }).agentSessionId
}

function parseToolArgs(argumentsJSON: string): Record<string, unknown> {
  if (!argumentsJSON) return {}
  try {
    const parsed: unknown = JSON.parse(argumentsJSON)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {}
  } catch {
    return {}
  }
}

/**
 * Build the provider-neutral voice tool catalog for a given HOST-derived execution
 * role. The serviceable surface is: the voice-surfaced control tools (role-gated —
 * coordinator-only tools are withheld from a leaf) plus the serviceable product
 * tools that the manifest ALSO marks as exposed on the `realtime_voice` surface.
 *
 * VT1 GATE. A product tool being serviceable (`WINDOWS_SERVICEABLE_PRODUCT_TOOLS`)
 * is necessary but NOT sufficient for voice: it must also declare `realtime_voice`
 * in `surfaces`, exactly like control tools do. This keeps raw/admin product tools
 * (`execute_sql`, `save_knowledge_graph`) OFF the voice surface — Mac does not voice-
 * expose them either — so a spoken request can never invoke them. They remain fully
 * available to the TYPED chat path via `WINDOWS_SERVICEABLE_PRODUCT_TOOLS`; this
 * only narrows what a warm voice session advertises.
 *
 * Non-serviceable manifest tools are omitted rather than advertised-then-degraded.
 * Pure + role-parameterized so it is unit-testable without a kernel.
 */
export function buildVoiceHubToolCatalog(
  executionRole: 'coordinator' | 'leaf'
): VoiceToolDeclaration[] {
  const out: VoiceToolDeclaration[] = []
  for (const entry of omiToolManifest) {
    const isControl = isAgentControlToolName(entry.name)
    const serviceable = isControl || WINDOWS_SERVICEABLE_PRODUCT_TOOLS.has(entry.name)
    if (!serviceable) continue
    // Every voice-advertised tool — control OR product — must be exposed on the
    // realtime_voice surface (the VT1 gate). This is where execute_sql /
    // save_knowledge_graph fall out: serviceable but desktop_chat-only.
    if (!entry.surfaces.includes('realtime_voice')) continue
    // An explicit voice opt-out (realtimeExpose:false) is honored for either kind.
    if (entry.voice?.realtimeExpose === false) continue
    // Control tools must ALSO pass the coordinator/leaf role gate. The dispatch layer
    // (handleAgentControlToolCall's leaf guard) re-enforces this; the catalog simply
    // never advertises what the role can't run.
    if (isControl && !isToolAvailableForContext(entry.adapters['pi-mono'], { executionRole })) {
      continue
    }
    out.push({
      name: entry.name,
      description: entry.voice?.realtimeDescription ?? entry.description,
      parameters: (entry.voice?.schemaOverride ?? entry.inputSchema) as unknown as Record<
        string,
        unknown
      >
    })
  }
  return out
}

/** The catalog for the voice surface: role read fresh from the main_chat session
 *  (host-derived). Empty until a signed-in owner exists (never advertise tools a
 *  disabled / signed-out hub could not run). */
export function readVoiceHubToolCatalog(
  deps: VoiceToolDeps = defaultDeps()
): VoiceToolDeclaration[] {
  if (!deps.ownerReady) return []
  const sessionId = mainChatSessionId(deps)
  const role = deps.kernel.executionPolicyForSession(sessionId).executionRole
  return buildVoiceHubToolCatalog(role)
}

/**
 * Execute one voice-requested tool in-process. Authority is host-derived from the
 * main_chat session (role/owner resolved fresh inside `executeHostTool`); the model
 * supplies only the name + arguments. Never throws — a failure is the returned
 * `"Error: …"` string (the provider tool-result contract).
 */
export async function executeVoiceHubTool(
  args: VoiceToolExecuteArgs,
  deps: VoiceToolDeps = defaultDeps()
): Promise<string> {
  // Require a signed-in owner (Mac `currentOwnerId()` throws otherwise). Fail closed
  // so a tool never runs — or keys a session — under the shared default owner.
  if (!deps.ownerReady) return 'Error: sign-in has not completed yet'
  const name = typeof args.name === 'string' ? args.name : ''
  if (!name) return 'Error: missing tool name'
  const input = parseToolArgs(args.argumentsJSON)
  const sessionId = mainChatSessionId(deps)
  return executeHostTool(name, input, {
    kernel: deps.kernel,
    sessionId,
    adapterId: MAIN_CHAT_ADAPTER_ID
  })
}

export function registerVoiceToolHandlers(): void {
  ipcMain.handle('voiceHub:toolCatalog', (): VoiceToolDeclaration[] => readVoiceHubToolCatalog())
  ipcMain.handle(
    'voiceHub:execute',
    (_e, args: VoiceToolExecuteArgs): Promise<string> => executeVoiceHubTool(args)
  )
}
