import { describe, expect, test } from 'vitest'
import { relationshipItems, routeIntent, orderFloorSections, type KindedSection } from './floorContext'

describe('relationshipItems', () => {
  test('renders a labeled edge as "Source — label → Target" using node labels', () => {
    const nodes = [
      { id: 'a', label: 'Omi Windows' },
      { id: 'b', label: 'TypeScript' }
    ]
    const edges = [{ sourceId: 'a', targetId: 'b', label: 'written in' }]
    expect(relationshipItems(nodes, edges)).toEqual(['Omi Windows — written in → TypeScript'])
  })

  test('drops edges whose endpoints are not in the node set', () => {
    const nodes = [{ id: 'a', label: 'Omi Windows' }]
    const edges = [
      { sourceId: 'a', targetId: 'ghost', label: 'uses' },
      { sourceId: 'missing', targetId: 'a', label: 'depends on' }
    ]
    expect(relationshipItems(nodes, edges)).toEqual([])
  })
})

describe('routeIntent', () => {
  test('routes a languages question to tech', () => {
    expect(routeIntent('what programming languages am I using?')).toEqual(['tech'])
  })

  test('routes an editor/app question to apps', () => {
    expect(routeIntent('what editor do I use')).toEqual(['apps'])
  })

  test('routes a "who do I work with" question to entities', () => {
    expect(routeIntent('who do I work with')).toEqual(['entities'])
  })

  test('returns no intent for an unrelated question', () => {
    expect(routeIntent('tell me a joke')).toEqual([])
  })

  test('orders multiple matches with relationships ahead of tech', () => {
    expect(routeIntent("how is my project's stack related")).toEqual([
      'relationships',
      'tech',
      'entities'
    ])
  })
})

describe('orderFloorSections', () => {
  const sections: KindedSection[] = [
    { kind: 'tech', heading: 'Programming languages & technologies', items: ['TypeScript'] },
    { kind: 'entities', heading: 'Projects, people & interests', items: ['Omi (project)'] },
    { kind: 'apps', heading: 'Installed apps', items: ['VS Code'] }
  ]

  test('leads with the question-relevant section and keeps the rest in order', () => {
    expect(orderFloorSections(sections, 'what editor do I use').map((s) => s.heading)).toEqual([
      'Installed apps',
      'Programming languages & technologies',
      'Projects, people & interests'
    ])
  })

  test('preserves the default order when nothing matches', () => {
    expect(orderFloorSections(sections, 'hello there').map((s) => s.heading)).toEqual([
      'Programming languages & technologies',
      'Projects, people & interests',
      'Installed apps'
    ])
  })

  test('strips the kind tag from the returned sections', () => {
    const out = orderFloorSections(sections, 'languages')
    expect(out.every((s) => !('kind' in s))).toBe(true)
  })
})
