/**
 * The auth bypass must be impossible to reach in a release build.
 *
 * `__DEV__` is a compile-time constant that Expo inlines, so gating on it is a
 * real guarantee rather than a runtime check that could be flipped. These tests
 * pin the shape of that gate so a future edit cannot quietly drop it -- the kind of
 * change that would otherwise leave a sign-in bypass in a shipped binary.
 */
describe('dev flags', () => {
  const load = (devValue: boolean, local?: string) => {
    jest.resetModules()
    process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN = local as string
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = devValue
    return require('./devFlags') as typeof import('./devFlags')
  }

  const savedEnv = process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN
  const savedEnv2 = process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN

  afterEach(() => {
    jest.resetModules()
    if (savedEnv === undefined) delete process.env.EXPO_PUBLIC_DEV_LOGIN_WITHOUT_ACCOUNT
    else process.env.EXPO_PUBLIC_DEV_LOGIN_WITHOUT_ACCOUNT = savedEnv
    if (savedEnv2 === undefined) delete process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN
    else process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN = savedEnv2
  })

  it('is off in a release build even when the env var is set', () => {
    const flags = load(false, '1')
    expect(flags.DEV_LOGIN_WITHOUT_ACCOUNT).toBe(false)
    expect(flags.DEV_LOCAL_BRAIN).toBe(false)
  })

  it('offers the no-account button in any dev build, with no env var needed', () => {
    // Deliberate asymmetry with DEV_LOCAL_BRAIN: a local session with no account
    // behind it is a dev convenience and must simply not exist in release, while
    // the dev screen route is extra and stays opt-in.
    const flags = load(true, undefined)
    expect(flags.DEV_LOGIN_WITHOUT_ACCOUNT).toBe(true)
    expect(flags.DEV_LOCAL_BRAIN).toBe(false)
  })

  it('is on in a dev build with an explicit opt-in for the dev screen', () => {
    const flags = load(true, '1')
    expect(flags.DEV_LOGIN_WITHOUT_ACCOUNT).toBe(true)
    expect(flags.DEV_LOCAL_BRAIN).toBe(true)
  })

  it('keeps the local-brain gate strict about its opt-in value', () => {
    expect(load(true, 'true').DEV_LOCAL_BRAIN).toBe(false)
    expect(load(true, 'yes').DEV_LOCAL_BRAIN).toBe(false)
  })
});