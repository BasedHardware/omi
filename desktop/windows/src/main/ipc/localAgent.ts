import { app, ipcMain } from 'electron'
import type {
  LocalAgentChatToolName,
  LocalAgentStatus,
  LocalAgentToolArguments,
  LocalAgentToolsTestResult
} from '../../shared/types'
import {
  copyLocalAgentToken,
  getLocalAgentStatus,
  rotateLocalAgentAccessToken,
  setLocalAgentEnabled,
  setLocalAgentPort,
  testLocalAgentTools
} from '../localAgent/control'
import { runLocalAgentTool, type LocalAgentRuntimeContext } from '../localAgent/tools'

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
  ipcMain.handle('localAgent:status', async (): Promise<LocalAgentStatus> => getLocalAgentStatus())
  ipcMain.handle(
    'localAgent:setEnabled',
    async (_e, enabled: boolean): Promise<LocalAgentStatus> =>
      setLocalAgentEnabled(enabled === true)
  )
  ipcMain.handle(
    'localAgent:setPort',
    async (_e, port: number): Promise<LocalAgentStatus> => setLocalAgentPort(port)
  )
  ipcMain.handle(
    'localAgent:copyToken',
    async (): Promise<LocalAgentStatus> => copyLocalAgentToken()
  )
  ipcMain.handle(
    'localAgent:rotateToken',
    async (): Promise<LocalAgentStatus> => rotateLocalAgentAccessToken()
  )
  ipcMain.handle(
    'localAgent:testTools',
    async (): Promise<LocalAgentToolsTestResult> => testLocalAgentTools()
  )
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
