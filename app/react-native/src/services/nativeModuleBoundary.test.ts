/**
 * Regression guard for the module boundary.
 *
 * requireNativeModule throws when a native module is absent rather than
 * returning null. local-calls called it at module scope with no guard, so simply
 * importing the file took down every importer -- HomeScreen via LocalBrainBar,
 * and every Jest test. local-brain had the same bug and was already fixed; these
 * two tests exist so neither can regress silently.
 *
 * require() rather than import(): a static require is evaluated when this file
 * loads, so a throw here fails the suite outright, which is the behaviour under
 * test. A dynamic import() also needs --experimental-vm-modules.
 */
describe('native module boundary', () => {
  it('imports local-calls cleanly with no native module present', () => {
    const m = require('../../modules/local-calls');
    expect(m.isCallDetectionAvailable).toBe(false);
  });

  it('imports local-brain cleanly with no native module present', () => {
    const m = require('../../modules/local-brain');
    expect(m.isLocalBrainAvailable).toBe(false);
  });

  it('reports permissions and refuses actions instead of throwing', async () => {
    const m = require('../../modules/local-calls');
    // Every one of these would be a TypeError on null if the null checks were
    // removed, and the UI calls all of them on mount.
    await expect(m.getCallPermissions()).resolves.toMatchObject({
      canDetect: false,
      canAnswer: false,
    });
    await expect(m.requestCallPermissions()).resolves.toMatchObject({
      canDetect: false,
    });
    await expect(m.startCallDetection(() => {})).resolves.toBe(false);
    await expect(m.answerCall()).resolves.toBe(false);
    await expect(m.hangUp()).resolves.toBe(false);
    await expect(m.stopCallDetection()).resolves.toBeUndefined();
  });

  it('routes through the heuristic when the native router is absent', async () => {
    const { routeWithProvider } = require('../services/localBrainRouter');
    const decision = await routeWithProvider('add a task: pay the electric bill', null);
    // Not that the native router exists -- it does not. That a missing provider
    // still produces a usable action is the property that keeps the app working
    // in Expo Go.
    expect(decision.source).toBe('heuristic');
    expect(decision.decision.kind).toBe('create_task');
  });
});
