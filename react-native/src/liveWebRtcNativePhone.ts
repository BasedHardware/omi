import type {LiveWebRtcScope} from './liveWebRtc';

type NativeWebRtcModule = {
  RTCPeerConnection?: unknown;
  MediaStream?: unknown;
  mediaDevices?: {
    getUserMedia(constraints: {audio: boolean}): Promise<unknown>;
  };
  registerGlobals?: () => void;
};

let registered = false;

/**
 * Phone-only WebRTC scope backed by react-native-webrtc (iOS/Android).
 * The module is loaded at runtime so typecheck never depends on the package's
 * generated declarations. Remote audio plays through the native WebRTC stack.
 */
export function resolveNativeLiveWebRtcScope(): LiveWebRtcScope | null {
  const webRtc = loadNativeWebRtc();
  if (webRtc === null) {
    return null;
  }
  const {RTCPeerConnection, MediaStream, mediaDevices, registerGlobals} =
    webRtc;
  if (typeof RTCPeerConnection !== 'function') {
    return null;
  }
  if (typeof mediaDevices?.getUserMedia !== 'function') {
    return null;
  }
  if (!registered) {
    try {
      registerGlobals?.();
    } catch {
      // Globals are optional when we pass an explicit LiveWebRtcScope.
    }
    registered = true;
  }
  return {
    RTCPeerConnection:
      RTCPeerConnection as LiveWebRtcScope['RTCPeerConnection'],
    navigator: {
      mediaDevices: {
        getUserMedia: (constraints: {audio: boolean}) =>
          mediaDevices.getUserMedia(constraints) as ReturnType<
            NonNullable<
              NonNullable<LiveWebRtcScope['navigator']>['mediaDevices']
            >['getUserMedia']
          >,
      },
    },
    // Native plays remote audio without an HTMLAudioElement.
    MediaStream: MediaStream as LiveWebRtcScope['MediaStream'],
  };
}

function loadNativeWebRtc(): NativeWebRtcModule | null {
  try {
    return require('react-native-webrtc') as NativeWebRtcModule;
  } catch {
    return null;
  }
}
