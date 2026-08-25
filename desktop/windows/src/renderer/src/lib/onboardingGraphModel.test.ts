import { describe, it, expect } from 'vitest'
import {
  USER_NODE_ID,
  slugId,
  buildUserNode,
  buildLanguage,
  buildApps
} from './onboardingGraphModel'

describe('onboardingGraphModel', () => {
  it('builds a person node for the user with a fixed id', () => {
    const n = buildUserNode('Ander')
    expect(n).toEqual({ id: 'user', label: 'Ander', nodeType: 'person' })
    expect(USER_NODE_ID).toBe('user')
  })

  it('builds a blue concept language node + prefers edge', () => {
    const { nodes, edges } = buildLanguage('en', 'English')
    expect(nodes).toEqual([
      { id: 'language_en', label: 'English', nodeType: 'concept', aliases: ['en'] }
    ])
    expect(edges).toEqual([
      { id: 'edge_user_language_en', sourceId: 'user', targetId: 'language_en', label: 'prefers' }
    ])
  })

  it('builds thing nodes + uses edges for apps with clean ids', () => {
    const { nodes, edges } = buildApps([{ name: 'VS Code' }, { name: 'Slack' }])
    expect(nodes).toEqual([
      { id: 'app_vs-code', label: 'VS Code', nodeType: 'thing' },
      { id: 'app_slack', label: 'Slack', nodeType: 'thing' }
    ])
    expect(edges).toEqual([
      { id: 'edge_user_app_vs-code', sourceId: 'user', targetId: 'app_vs-code', label: 'uses' },
      { id: 'edge_user_app_slack', sourceId: 'user', targetId: 'app_slack', label: 'uses' }
    ])
  })

  it('slugId lowercases, trims, and dashes non-alphanumerics', () => {
    expect(slugId('Adobe  Photoshop 2024!')).toBe('adobe-photoshop-2024')
  })

  it('skips apps with empty names', () => {
    const { nodes } = buildApps([{ name: '  ' }, { name: 'Figma' }])
    expect(nodes).toEqual([{ id: 'app_figma', label: 'Figma', nodeType: 'thing' }])
  })
})
