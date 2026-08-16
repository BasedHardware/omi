import { describe, expect, it } from 'vitest'
import { detectAgentTask, explicitPathIn, folderHintIn, resolveTaskCwd } from './agentTask'

describe('detectAgentTask', () => {
  it('detects every agent by name behind a delegation verb', () => {
    expect(detectAgentTask('ask codex to add a readme')).toEqual({
      agentId: 'codex',
      prompt: 'ask codex to add a readme'
    })
    expect(detectAgentTask('use claude code to create a hello world script')?.agentId).toBe('acp')
    expect(detectAgentTask('have openclaw fix the failing test in my omi repo')?.agentId).toBe(
      'openclaw'
    )
    expect(detectAgentTask('tell hermes to summarize the changelog')?.agentId).toBe('hermes')
    expect(detectAgentTask('delegate this to hermes please')?.agentId).toBe('hermes')
  })

  it('detects a leading agent name ("codex, fix …")', () => {
    expect(detectAgentTask('codex, fix the flaky retry test')?.agentId).toBe('codex')
    expect(detectAgentTask('hey claude code: add input validation')?.agentId).toBe('acp')
    expect(detectAgentTask('open claw - run the linter and fix warnings')?.agentId).toBe('openclaw')
  })

  it('prefers the longer alias ("claude code" over "claude")', () => {
    expect(detectAgentTask('use claude code to refactor this')?.agentId).toBe('acp')
    expect(detectAgentTask('ask claude to refactor this')?.agentId).toBe('acp')
  })

  it('detects unnamed delegation ("ask an agent …") with no agentId', () => {
    expect(detectAgentTask('ask a coding agent to clean up the imports')).toEqual({
      agentId: undefined,
      prompt: 'ask a coding agent to clean up the imports'
    })
    expect(detectAgentTask('have an agent write the release notes')?.agentId).toBeUndefined()
  })

  it('leaves guidance questions and plain chat alone', () => {
    expect(detectAgentTask('what can codex do?')).toBeNull()
    expect(detectAgentTask('how do I use claude code?')).toBeNull()
    expect(detectAgentTask('should I use hermes for this?')).toBeNull()
    expect(detectAgentTask('remind me to buy milk')).toBeNull()
    expect(detectAgentTask('I met Claude yesterday at the conference')).toBeNull()
    expect(detectAgentTask('')).toBeNull()
  })
})

describe('working-directory extraction', () => {
  it('finds an explicit absolute Windows path', () => {
    expect(explicitPathIn('ask codex to fix C:\\work\\omi\\app please')).toBe('C:\\work\\omi\\app')
    expect(explicitPathIn('use claude code in D:/projects/site')).toBe('D:/projects/site')
    expect(explicitPathIn('no path here')).toBeUndefined()
  })

  it('finds a folder-name hint', () => {
    expect(folderHintIn('fix the failing test in my omi repo')).toBe('omi')
    expect(folderHintIn('add a readme to the desktop-windows project')).toBe('desktop-windows')
    expect(folderHintIn('just chat, no folders')).toBeUndefined()
  })

  it('resolves: explicit path > hinted indexed folder > most recent folder > undefined', async () => {
    const sqlQueries: string[] = []
    const deps = {
      searchFiles: async (q: string) =>
        q === 'omi' ? [{ folder: 'C:\\Users\\me\\projects\\omi' }] : [],
      executeSql: async (sql: string) => {
        sqlQueries.push(sql)
        return {
          columns: ['folder', 'last_modified'],
          rows: [{ folder: 'C:\\Users\\me\\recent-project', last_modified: 123 }]
        }
      }
    }
    expect(await resolveTaskCwd('fix C:\\explicit\\path now', deps)).toBe('C:\\explicit\\path')
    expect(await resolveTaskCwd('fix the failing test in my omi repo', deps)).toBe(
      'C:\\Users\\me\\projects\\omi'
    )
    expect(await resolveTaskCwd('fix the failing test', deps)).toBe('C:\\Users\\me\\recent-project')
    // The recency query must skip app shortcuts, or "most recent folder"
    // resolves to a Start-Menu vendor folder (seen live: ...\Programs\McAfee).
    expect(sqlQueries.at(-1)).toContain("file_type != 'application'")

    const failing = {
      searchFiles: async () => {
        throw new Error('no index')
      },
      executeSql: async () => {
        throw new Error('no db')
      }
    }
    expect(await resolveTaskCwd('fix the failing test in my omi repo', failing)).toBeUndefined()
  })
})
