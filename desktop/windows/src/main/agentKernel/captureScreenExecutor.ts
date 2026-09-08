// The `capture_screen` product-tool executor + its toggle gate.
//
// This is the Windows analogue of macOS' ChatToolExecutor.policyFor(...) case for
// "capture_screen"/"get_screenshot" (ChatToolExecutor.swift:490-504): the user's
// "Screen Sharing in Chat" setting (chatScreenshotSharingEnabled, default ON) is
// the consent gate, checked at DISPATCH — the model can only capture the screen
// when the setting is on. On Mac the check returns .allow / .deny before
// executeCaptureScreen runs; here the gate lives at the top of the executor the
// tool relay dispatches to, so it is enforced at the relay layer, not merely in UI.
//
// When the gate is off we return the SAME "POLICY_DENIED: <json>" shape Mac emits
// (code disabled_by_user_setting, capability desktop.context.screenshot_image) so
// the model gets an identical, machine-readable refusal telling it to ask the user
// to enable the setting — the only platform-specific difference is the Settings
// location (Windows: Privacy; Mac: Floating Bar).

import { getAppSettings } from '../appSettings'
import { captureScreenToFile } from './screenCapture'
import type { ProductToolExecutor } from './toolRelayBridge'

export const CAPTURE_SCREEN_TOOL = 'capture_screen'
export const SCREENSHOT_IMAGE_CAPABILITY = 'desktop.context.screenshot_image'

/**
 * The refusal returned when Screen Sharing in Chat is off. Mirrors macOS'
 * ChatToolExecutor.policyDeniedMessage — a `POLICY_DENIED:` prefix followed by
 * sorted-key JSON, so the model can parse the same fields on both platforms.
 */
export function screenshotSharingDeniedMessage(): string {
  // Keys are emitted in sorted order to match Swift's JSONSerialization .sortedKeys.
  const payload = {
    capability: SCREENSHOT_IMAGE_CAPABILITY,
    code: 'disabled_by_user_setting',
    message:
      'Screenshot sharing is turned off. The user can enable "Screen Sharing in Chat" in Settings → Privacy to let Omi see the screen.',
    ok: false,
    tool: CAPTURE_SCREEN_TOOL
  }
  return `POLICY_DENIED: ${JSON.stringify(payload)}`
}

export interface CaptureScreenExecutorDeps {
  /** Reads the persisted consent toggle. Defaults to the real app setting. */
  isSharingEnabled: () => boolean
  /** Performs the capture and returns the file path. Defaults to the real capture. */
  capture: () => Promise<string>
}

/**
 * Build the `capture_screen` executor. Deps are injectable so the gate can be
 * tested without Electron or the filesystem; production binds them to the real
 * app setting and screen capture.
 */
export function createCaptureScreenExecutor(
  deps?: Partial<CaptureScreenExecutorDeps>
): ProductToolExecutor {
  const isSharingEnabled =
    deps?.isSharingEnabled ?? (() => getAppSettings().chatScreenshotSharingEnabled)
  const capture = deps?.capture ?? captureScreenToFile
  return async () => {
    if (!isSharingEnabled()) return screenshotSharingDeniedMessage()
    return capture()
  }
}
