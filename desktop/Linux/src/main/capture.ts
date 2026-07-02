import { app, desktopCapturer, screen, ipcMain, session } from 'electron'
import type { ScreenshotResult } from '../shared/types'

// Screen capture equivalents of ScreenCaptureService.swift. Screenshots come from
// desktopCapturer thumbnails; system audio comes from the display-media loopback
// handler (the SystemAudioCaptureService counterpart). On Windows this was WASAPI
// loopback; on Linux it routes through Chromium's PulseAudio monitor-source path
// (see installLoopbackAudioHandler).

// Linux system-audio loopback over getDisplayMedia is gated behind a Chromium
// feature flag that is off by default and only implemented for the PulseAudio
// backend (it captures the default sink's monitor source). It must be enabled
// before the app is ready, so we append it at module load (this module is
// imported before app.whenReady() resolves). On a PipeWire-only/ALSA host with
// no PulseAudio (or pipewire-pulse) layer the flag is inert, Chromium simply
// delivers no audio track, so this is a safe no-op there. We still pass
// useSystemPicker:false to keep seamless, picker-less meeting capture.
if (process.platform === 'linux') {
  app.commandLine.appendSwitch('enable-features', 'PulseaudioLoopbackForScreenShare')
}

const JPEG_QUALITY = 80
const MAX_DIMENSION = 3000

export async function captureScreenshot(): Promise<ScreenshotResult | null> {
  const display = screen.getPrimaryDisplay()
  const { width, height } = display.size
  const scale = Math.min(1, MAX_DIMENSION / Math.max(width, height))
  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: Math.round(width * scale), height: Math.round(height * scale) }
  })
  const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0]
  if (!source || source.thumbnail.isEmpty()) return null
  const img = source.thumbnail
  const size = img.getSize()
  return {
    dataUrl: `data:image/jpeg;base64,${img.toJPEG(JPEG_QUALITY).toString('base64')}`,
    width: size.width,
    height: size.height
  }
}

// Defense-in-depth: getDisplayMedia auto-resolves to screen + loopback audio
// without a picker (needed for seamless meeting capture), so we only honor a
// request the app itself armed within the last few seconds. A compromised
// renderer calling getDisplayMedia out of band gets denied → can't silently
// record the screen/system audio.
let captureArm: { until: number; processId: number; frameId: number } | null = null
const ARM_WINDOW_MS = 5000

export function registerCaptureIpc(): void {
  ipcMain.handle('capture:screenshot', () => captureScreenshot())
  ipcMain.on('capture:arm-loopback', (event) => {
    captureArm = {
      until: Date.now() + ARM_WINDOW_MS,
      processId: event.processId,
      frameId: event.frameId
    }
  })
}

export function installLoopbackAudioHandler(): void {
  session.defaultSession.setDisplayMediaRequestHandler(
    (request, callback) => {
      if (
        !captureArm ||
        Date.now() > captureArm.until ||
        request.frame?.processId !== captureArm.processId ||
        request.frame?.routingId !== captureArm.frameId
      ) {
        // Not an app-initiated capture, deny.
        callback({})
        return
      }
      captureArm = null
      // Linux: request audio:'loopback' (PulseAudio monitor source), but treat it
      // as best-effort. Unlike Windows WASAPI, loopback is unavailable on
      // PipeWire-only/ALSA hosts; in that case Chromium just drops the audio track
      // and keeps the video track, so the response stays valid. Crucially we
      // ALWAYS return the video source, never gate it on audio, and the callback
      // never throws (getSources rejection still yields a defined callback). When
      // no system-audio track materializes, live conversation falls back to
      // microphone capture in the renderer.
      desktopCapturer.getSources({ types: ['screen'] }).then(
        (sources) => callback(sources[0] ? { video: sources[0], audio: 'loopback' } : {}),
        () => callback({})
      )
    },
    { useSystemPicker: false }
  )
}
