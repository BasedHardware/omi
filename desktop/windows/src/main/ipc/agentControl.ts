// IPC surface for the agent control plane.
//
// This is the trusted-direct-control boundary: the app's own UI calling the
// agent-control tools, equivalent to macOS' Swift host calling `control(name,
// args)`. The renderer is the user's own interface, so a call arriving here
// carries the user's authority — which is what lets it resolve a dispatch.
//
// That authority is exactly why this channel exposes NO way to change WHO the
// caller is. See the owner note below.
//
// A model NEVER reaches this channel. When a model-facing tool loop lands it
// must build its own AgentControlToolContext with `trustedUserControl: false`
// and the caller's real executionRole, and advertise only the tools
// `agentControlToolDefinitionsFor()` returns for it.

import { ipcMain } from 'electron'
import { agentControlToolDefinitionsFor, isAgentControlToolName } from '../agentKernel/controlTools'
import { callAgentControlTool } from '../agentKernel/controlPlane'

// NO OWNER SETTER HERE, DELIBERATELY. The active owner is the identity every
// control call's data is scoped to, so the renderer must not be able to set it:
// a compromised or buggy renderer could point the kernel at an arbitrary owner
// string, and the per-call owner guard is no defense because it compares against
// whatever the renderer just set. That would be a cross-account local-data read
// on a shared machine the moment a second owner's rows exist.
//
// The owner is host state (`setControlPlaneOwner`, main-side only). It stays the
// single local owner until main itself owns auth; wire it there — never over IPC.

export function registerAgentControlIpc(): void {
  ipcMain.handle(
    'agentControl:call',
    async (_e, name: string, input: Record<string, unknown> = {}): Promise<string> => {
      if (typeof name !== 'string' || !isAgentControlToolName(name)) {
        return JSON.stringify({
          ok: false,
          error: { code: 'unknown_control_tool', message: `Unknown control tool: ${name}` }
        })
      }
      return callAgentControlTool(name, input ?? {})
    }
  )

  // What this caller may see. Trusted direct control sees every tool; this is
  // here so the UI can render the capability surface without hardcoding it.
  ipcMain.handle('agentControl:tools', () =>
    agentControlToolDefinitionsFor({ trustedUserControl: true, executionRole: 'coordinator' })
  )
}
