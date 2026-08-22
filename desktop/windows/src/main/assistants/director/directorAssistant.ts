/**
 * The director's coordinator peer — the mount point where screen frames and
 * context switches enter the subsystem (mac: ProactiveAssistantsPlugin ->
 * AssistantCoordinator.checkContextSwitch).
 *
 * Registration is unconditional and analyze() is a cheap frame-tracking write;
 * the two pipelines gate themselves: the buckets path on
 * `contextDirectorEnabled`, the TCRS legacy path on that same flag being OFF
 * (mac's exact inversion). A privacy-denied arrival (null title from the
 * coordinator contract) closes the visit as excluded and produces no event.
 */

import type { ProactiveAssistant } from '../core/coordinator'
import type { RewindFrame } from '../../../shared/types'
import {
  directorPipelineEnabled,
  directorTcrs,
  directorSubjectBinding,
  directorVisits,
  directorEngine,
  recordTrackedFrame,
  clearTrackedFrame,
  runDepartureExtraction,
  wireDirectorSessionReset
} from './service'
import { appWindowEvent } from './tcrs'

export class DirectorAssistant implements ProactiveAssistant {
  readonly identifier = 'director'
  readonly displayName = 'Context Director'

  isEnabled(): boolean {
    // Frame tracking must stay live for both pipelines; each gates itself.
    return true
  }

  shouldAnalyze(): boolean {
    return true
  }

  needsFrameDuringDelay(): boolean {
    return true
  }

  async analyze(frame: RewindFrame): Promise<null> {
    recordTrackedFrame(frame)
    return null
  }

  handleResult(): void {
    // Results deliver via side effects (the engine notifies through
    // notifyProactive); analyze() never returns one.
  }

  async onContextSwitch(
    departingFrame: RewindFrame | null,
    newApp: string,
    newWindowTitle: string | null
  ): Promise<void> {
    wireDirectorSessionReset()

    if (directorPipelineEnabled()) {
      if (newWindowTitle === null && newApp.length === 0) {
        await directorVisits.leaveForExcludedContext(departingFrame?.id ?? null)
        return
      }
      if (newWindowTitle === null) {
        // Privacy-denied arrival: close the departing visit, open nothing.
        await directorVisits.leaveForExcludedContext(departingFrame?.id ?? null)
        return
      }
      const result = await directorVisits.transition({
        toApp: newApp,
        toWindowTitle: newWindowTitle,
        handles: [],
        processName: departingFrame?.processName ?? null,
        departingFrameId: departingFrame?.id ?? null
      })
      if (result.departed?.outcome === 'completed' && departingFrame !== null) {
        void runDepartureExtraction(result.departed.fence, departingFrame)
      }
      void directorEngine.contextEntered(result.arriving)
      return
    }

    // Legacy path (buckets off): the TCRS app_window producer.
    if (newWindowTitle === null) return
    const event = appWindowEvent({
      appName: newApp,
      windowTitle: newWindowTitle,
      occurredAt: Date.now()
    })
    if (event === null) return
    directorTcrs.observe(directorSubjectBinding.resolve(event))
  }

  clearPendingWork(): void {
    clearTrackedFrame()
  }

  stop(): void {
    clearTrackedFrame()
  }
}

let singleton: DirectorAssistant | null = null

export function getDirectorAssistant(): DirectorAssistant {
  if (singleton === null) singleton = new DirectorAssistant()
  return singleton
}
