import { app, ipcMain } from 'electron'
import { runLocalAgentTool, type LocalAgentRuntimeContext } from '../localAgent/tools'
import type { LocalAgentChatToolName, LocalAgentToolArguments } from '../../shared/types'

const CHAT_CONTEXT_TOOLS = new Set<LocalAgentChatToolName>([
  'get_local_status',
  'search_screen_history',
  'execute_sql',
  'get_screenshot'
])

function runtimeContext(): LocalAgentRuntimeContext {
  return {
    localUrl: 'omi://local-agent',
    toolEndpoint: 'omi://local-agent/chat-context-tool',
    app: {
      name: app.getName(),
      version: app.getVersion(),
      appId: 'com.omiwindows.app'
    }
  }
}

export function registerLocalAgentHandlers(): void {
  ipcMain.handle(
    'localAgent:chatTool',
    async (_event, name: string, args?: LocalAgentToolArguments) => {
      if (!CHAT_CONTEXT_TOOLS.has(name as LocalAgentChatToolName)) {
        throw new Error('Local tool is not available to chat context')
      }
      return runLocalAgentTool(name, args ?? {}, runtimeContext())
    }
  )
}
