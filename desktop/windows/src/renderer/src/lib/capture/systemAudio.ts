// System-audio (loopback) capture, extracted verbatim from omiListenClient.ts so
// the capture layer owns every getUserMedia/getDisplayMedia entry point in one
// place. Behavior is unchanged — Windows returns the loopback via getDisplayMedia
// with the video track requested (audio-only display capture is rejected), so we
// grab audio then immediately drop the video track.

/** Capture the system/loopback audio as a mic-shaped MediaStream (audio tracks
 *  only). Throws with actionable text when the main-process display-media handler
 *  isn't active or Windows yields no loopback track. */
export async function getSystemAudioStream(): Promise<MediaStream> {
  let display: MediaStream
  try {
    display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
  } catch (e) {
    const err = e as Error
    if (/not supported/i.test(err.message)) {
      throw new Error(
        'System-audio capture handler not active. Fully restart the app (stop and rerun `npm run dev`) so the main process reloads.'
      )
    }
    throw e
  }
  const audioTracks = display.getAudioTracks()
  display.getVideoTracks().forEach((t) => t.stop())
  if (audioTracks.length === 0) {
    throw new Error('Windows returned no system-audio (loopback) track.')
  }
  return new MediaStream(audioTracks)
}
