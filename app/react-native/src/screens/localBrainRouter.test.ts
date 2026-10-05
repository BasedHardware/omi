import {
  routeWithProvider,
  ROUTE_PROTOTYPES,
  type Route,
  type RouteProvider,
} from '../services/localBrainRouter'

/** A provider that returns a fixed route, for exercising each branch. */
function fixed(route: Route, margin = 0.4, declined = false): RouteProvider {
  return { route: async () => ({ route, margin, declined }) }
}

describe('routeWithProvider composition', () => {
  it('uses the router for the kind and the regexes for the title', async () => {
    const out = await routeWithProvider('add a task: pay the electric bill', fixed('create_task'))
    expect(out.source).toBe('router')
    expect(out.decision).toEqual({ kind: 'create_task', title: 'pay the electric bill' })
  })

  it('lets a confident router "chat" beat a keyword hit', async () => {
    // The regex alone would call this a task. If the router is confident it is a
    // question, the router wins -- otherwise adding it changes nothing.
    const out = await routeWithProvider('add a task: pay the electric bill', fixed('chat', 0.55))
    expect(out.source).toBe('router')
    expect(out.decision.kind).toBe('chat')
  })

  it('fills reminder timing from the text, not the router', async () => {
    const out = await routeWithProvider('remind me to stretch in 20 minutes', fixed('create_reminder'))
    expect(out.decision).toEqual({
      kind: 'create_reminder',
      title: 'stretch',
      minutesFromNow: 20,
    })
  })

  it('overrides the regex kind when the router disagrees', async () => {
    // Regex says reminder (it saw "remind me"); router says task. The router is
    // the component added to improve routing, so it wins on kind.
    const out = await routeWithProvider('remind me to buy milk', fixed('create_task'))
    expect(out.decision).toEqual({ kind: 'create_task', title: 'buy milk' })
  })

  it('degrades to the heuristic when the router declines', async () => {
    const out = await routeWithProvider('add a task: book flights', fixed('create_task', 0.004, true))
    expect(out.source).toBe('heuristic')
    expect(out.decision).toEqual({ kind: 'create_task', title: 'book flights' })
  })

  it('degrades when there is no provider or it throws', async () => {
    const none = await routeWithProvider('add a task: book flights', null)
    expect(none.source).toBe('heuristic')

    const threw: RouteProvider = {
      route: async () => {
        throw new Error('model not loaded')
      },
    }
    const fallback = await routeWithProvider('add a task: book flights', threw)
    expect(fallback.source).toBe('heuristic')
    expect(fallback.decision).toEqual({ kind: 'create_task', title: 'book flights' })
  })

  it('never invents a title when the router commits but nothing can be extracted', async () => {
    // Routing says "task", but there is no verb and therefore no title. Handing
    // back an empty title would be a silent no-op the user cannot debug.
    const out = await routeWithProvider('the electricity bill is due friday', fixed('create_task'))
    expect(out.source).toBe('heuristic')
    expect(out.decision.kind).toBe('chat')
  })

  it('handles empty input without throwing', async () => {
    const out = await routeWithProvider('', fixed('chat'))
    expect(out.decision).toEqual({ kind: 'chat', text: '' })
  })
})

describe('prototype bank', () => {
  it('covers every route and contains no antonym pair', () => {
    expect(Object.keys(ROUTE_PROTOTYPES).sort()).toEqual(['chat', 'create_reminder', 'create_task'])
    for (const [route, protos] of Object.entries(ROUTE_PROTOTYPES)) {
      expect(protos.length).toBeGreaterThanOrEqual(5)
      for (const p of protos) expect(p.length).toBeGreaterThan(10)
      expect(`${route}:${protos.join(' ')}`.toLowerCase()).toBeTruthy()
    }
  })

  it('does not contain a negation, which the router cannot handle lexically', async () => {
    // The native router gates negation ahead of inference. If a prototype ever
    // taught it "don't ..." the two guards would disagree.
    const all = Object.values(ROUTE_PROTOTYPES).flat().join(' ').toLowerCase()
    expect(all).not.toMatch(/don'?t|do not|never/)
  })
})