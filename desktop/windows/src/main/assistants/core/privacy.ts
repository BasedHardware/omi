// The screenshot privacy gate every proactive assistant runs behind.
//
// Capture already drops excluded apps, sensitive window titles, the lock screen
// and near-duplicates (`rewind/captureDecision.ts`). This is the SECOND filter —
// the one the renderer's Insight engine applies on top (`screenRedact.ts`):
// private/incognito windows, and denied contexts (password managers, banks,
// login pages). It matters more here than it does for Insight: an assistant may
// ship the frame's actual PIXELS to a cloud model, where Insight only ever sent
// OCR text.
//
// Pure — no fs, no state. `frame.imagePath` is never read here.
import { isDeniedContext, isPrivateWindow } from '../../../shared/screenPrivacy'
import type { RewindFrame } from '../../../shared/types'

/** Whether an assistant may look at this frame at all. */
export function mayAnalyzeFrame(
  frame: Pick<RewindFrame, 'app' | 'windowTitle' | 'processName'>
): boolean {
  if (isPrivateWindow(frame.windowTitle)) return false
  return !isDeniedContext({
    app: frame.app,
    windowTitle: frame.windowTitle,
    processName: frame.processName
  })
}
