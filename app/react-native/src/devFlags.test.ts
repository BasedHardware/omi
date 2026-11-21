/**
 * Guest mode is not gated on __DEV__ any more -- a release build is a legitimate
 * place for a guest session, and gating it on __DEV__ meant the release APK, the
 * one build that opens without a dev server, was the one you could not get into.
 *
 * What still must not ship is the dev-only screens, which are gated twice:
 * __DEV__ and an explicit opt-in.
 */
describe('flags', () => {
  const savedEnv = process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN

  afterEach(() => {
    jest.resetModules()
    if (savedEnv === undefined) delete process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN
    else process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN = savedEnv
  })

  const load = (dev: boolean, local?: string) => {
    jest.resetModules()
    process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN = local as string
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = dev
    return require('./devFlags') as typeof import('./devFlags')
  }

  it('keeps the dev screens off in a release build even when opted in', () => {
    expect(load(false, '1').DEV_LOCAL_BRAIN).toBe(false)
  })

  it('keeps the dev screens off in a dev build without the opt-in', () => {
    expect(load(true, undefined).DEV_LOCAL_BRAIN).toBe(false)
  })

  it('enables the dev screens in a dev build with the opt-in', () => {
    expect(load(true, '1').DEV_LOCAL_BRAIN).toBe(true)
  })

  it('requires the opt-in to be exactly "1"', () => {
    expect(load(true, 'true').DEV_LOCAL_BRAIN).toBe(false)
    expect(load(true, 'yes').DEV_LOCAL_BRAIN).toBe(false)
  })

  it('still exposes guest mode in a release build', () => {
    // The regression this guards: __DEV__-gating the button meant the release
    // APK could not be opened at all without an account.
    expect(load(false).GUEST_MODE).toBe(true)
  })
})