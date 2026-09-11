import {
  MediaStream,
  RTCPeerConnection,
  mediaDevices,
  registerGlobals,
} from 'react-native-webrtc';

import type {LiveWebRtcScope} from './liveWebRtc';

let registered = false;

/**
 * Phone-only WebRTC scope backed by react-native-webrtc (iOS/Android).
 * Remote audio tracks play through the native WebRTC stack — no HTML Audio.
 */
export function resolveNativeLiveWebRtcScope(): LiveWebRtcScope | null {
  if (typeof RTCPeerConnection !== 'function') {
    return null;
  }
  if (typeof mediaDevices?.getUserMedia !== 'function') {
    return null;
  }
  if (!registered) {
    try {
      registerGlobals();
    } catch {
      // Globals are optional when we pass an explicit LiveWebRtcScope.
    }
    registered = true;
  }
  return {
    RTCPeerConnection:
      RTCPeerConnection as unknown as LiveWebRtcScope['RTCPeerConnection'],
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
    MediaStream: MediaStream as unknown as LiveWebRtcScope['MediaStream'],
  };
}
