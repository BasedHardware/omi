// Orb harness — rAF self-throttle check on the app's real OrbAnimator:
//   idle    → ~30fps
//   active  → ~60fps (thinking)
//   hidden  → 0fps (loop fully stopped)
// Asserts the animator's frame-timestamp log matches each throttle state.
// Run: node scripts/orb/check-throttle.mjs  (exit 1 on failure)
import { openHarness } from './lib/harness.mjs'

const SETTLE_MS = 300
const WINDOW_MS = 2000

async function measure(page) {
  await page.evaluate(() => window.orb.liveClearLog())
  await page.waitForTimeout(WINDOW_MS)
  const log = await page.evaluate(() => window.orb.liveFrameLog())
  if (log.length < 2) return log.length === 0 ? 0 : 1
  return ((log.length - 1) / (log[log.length - 1] - log[0])) * 1000
}

async function main() {
  const { page, close } = await openHarness('?live=1&state=idle')
  const failures = []
  try {
    await page.waitForTimeout(SETTLE_MS)
    const idleFps = await measure(page)
    if (idleFps < 24 || idleFps > 38) failures.push(`idle fps ${idleFps.toFixed(1)} not ~30`)

    await page.evaluate(() => window.orb.liveSetState('thinking'))
    await page.waitForTimeout(SETTLE_MS)
    const activeFps = await measure(page)
    if (activeFps < 48 || activeFps > 75)
      failures.push(`active fps ${activeFps.toFixed(1)} not ~60`)

    await page.evaluate(() => window.orb.liveSetVisible(false))
    await page.waitForTimeout(SETTLE_MS)
    const hiddenFps = await measure(page)
    if (hiddenFps !== 0) failures.push(`hidden fps ${hiddenFps.toFixed(1)} — loop must fully stop`)

    // Resumes when visible again.
    await page.evaluate(() => window.orb.liveSetVisible(true))
    await page.waitForTimeout(SETTLE_MS)
    const resumedFps = await measure(page)
    if (resumedFps < 24) failures.push(`resumed fps ${resumedFps.toFixed(1)} — did not restart`)

    console.log(
      `[orb-throttle] idle ${idleFps.toFixed(1)}fps · active ${activeFps.toFixed(1)}fps · hidden ${hiddenFps.toFixed(1)}fps · resumed ${resumedFps.toFixed(1)}fps`
    )
  } finally {
    await close()
  }
  if (failures.length) {
    console.error('[orb-throttle] FAIL:')
    for (const f of failures) console.error('  - ' + f)
    process.exit(1)
  }
  console.log('[orb-throttle] PASS — 30 idle / 60 active / 0 hidden')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
