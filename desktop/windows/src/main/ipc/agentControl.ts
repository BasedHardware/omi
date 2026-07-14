// IPC surface for the agent control plane.
//
// This is the trusted-direct-control boundary: the app's own UI calling the
// agent-control tools, equivalent to macOS' Swift host calling `control(name,
// args)`. The renderer is the user's own interface, so a call arriving here
// carries the user's authority — which is what lets it resolve a dispatch.
//
// A model NEVER reaches this channel. When a model-facing tool loop lands it
// must build its own AgentControlToolContext with `trustedUserControl: false`
// and the caller's real executionRole, and advertise only the tools
// `agentControlToolDefinitionsFor()` returns for it.

import { ipcMain } from 'electron'
import {
  agentControlToolDefinitionsFor,
  isAgentControlToolName
} from '../agentKernel/controlTools'
import { callAgentControlTool, setControlPlaneOwner } from '../agentKernel/controlPlane'

export function registerAgentControlIpc(): void {
  // The authoritative owner for every subsequent control call. Auth lives in the
  // renderer, so it hands the signed-in uid to main once; per-call ownerId stays
  // a guard only (see controlPlane.ts).
  ipcMain.handle('agentControl:setOwner', (_e, ownerId: string | null) => {
    setControlPlaneOwner(ownerId)
  })

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
