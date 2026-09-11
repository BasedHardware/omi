import type {LiveWebRtcScope} from './liveWebRtc';

/** Default platform stub — web uses globalThis; macos stays unsupported. */
export function resolveNativeLiveWebRtcScope(): LiveWebRtcScope | null {
  return null;
}
