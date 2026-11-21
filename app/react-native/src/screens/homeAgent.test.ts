import { interpretCommand, runAgent, type LocalModel } from '../services/localAgent'

describe('localAgent.interpretCommand', () => {
  it('recognises task verbs and strips the verb', () => {
    expect(interpretCommand('add a task: pay the electric bill')).toEqual({
      kind: 'create_task',
      title: 'pay the electric bill',
    })
    expect(interpretCommand('write a to-do call mum').kind).toBe('create_task')
    expect(interpretCommand('create task book flights').kind).toBe('create_task')
  })

  it('recognises reminders and parses an "in N" duration', () => {
    expect(interpretCommand('remind me to stretch in 20 minutes')).toEqual({
      kind: 'create_reminder',
      title: 'stretch',
      minutesFromNow: 20,
    })
    const hour = interpretCommand('remind me to leave in 1 hour')
    expect(hour.kind === 'create_reminder' && hour.minutesFromNow).toBe(60)
  })

  it('routes plain questions to chat', () => {
    expect(interpretCommand('what did I say about the laya project')).toEqual({
      kind: 'chat',
      text: 'what did I say about the laya project',
    })
    expect(interpretCommand('')).toEqual({ kind: 'chat', text: '' })
  })

  it('is case-insensitive and does not create a task with an empty title', () => {
    expect(interpretCommand('ADD A TASK:').kind).toBe('chat')
  })
})

describe('localAgent.runAgent with a LocalModel', () => {
  const modelReturning = (json: string): LocalModel => ({
    complete: async () => json
  })

  it('uses the model when it returns a valid task JSON', async () => {
    const a = await runAgent(
      'I need to renew my passport',
      modelReturning('{"kind":"create_task","title":"renew passport"}')
    )
    expect(a).toEqual({ kind: 'create_task', title: 'renew passport' })
  })

  it('falls back to the heuristic if the model output is unparseable', async () => {
    const a = await runAgent('add a task: buy milk', modelReturning('not json at all'))
    expect(a).toEqual({ kind: 'create_task', title: 'buy milk' })
  })

  it('falls back to chat when there is no model and no command match', async () => {
    const a = await runAgent('tell me a joke')
    expect(a.kind).toBe('chat')
  })

  it('degrades to heuristic when the model throws', async () => {
    const boom: LocalModel = { complete: async () => { throw new Error('no model') } }
    const a = await runAgent('create reminder water plants', boom)
    expect(a.kind).toBe('create_task') // heuristic "create ... reminder" -> create_task path
  })
})
