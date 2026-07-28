// The coding agents Omi can delegate to — Claude Code (built in) plus the
// external CLIs the user configures in Settings. Shared by the Settings → Agents
// tab and the bar's list view so the fetch + refresh-on-command-change logic
// lives in one place (was duplicated verbatim). Fetches on mount and whenever the
// launch commands change, so a freshly-connected agent shows without a restart;
// `refresh` re-lists on demand for callers that just mutated the commands.
import { useCallback, useEffect, useState } from 'react'
import { getPreferences, onPreferencesChange } from '../lib/preferences'
import type { CodingAgentInfo } from '../../../shared/types'

export function useCodingAgents(): { agents: CodingAgentInfo[]; refresh: () => void } {
  const [agents, setAgents] = useState<CodingAgentInfo[]>([])
  const refresh = useCallback((): void => {
    void window.omi
      .codingAgentList(getPreferences().agentCommands)
      .then(setAgents)
      .catch(() => setAgents([]))
  }, [])
  useEffect(refresh, [refresh])
  useEffect(() => onPreferencesChange(refresh), [refresh])
  return { agents, refresh }
}
