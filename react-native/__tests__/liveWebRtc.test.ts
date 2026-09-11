import {
  LiveWebRtcSession,
  resolveLiveWebRtcScope,
  type LiveVoicePhase,
  type LiveWebRtcScope,
} from '../src/liveWebRtc';

class FakeDataChannel {
  readyState = 'open';
  sent: string[] = [];
  closed = false;
  private listeners: Array<(event: {data: unknown}) => void> = [];
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
    this.readyState = 'closed';
  }
  addEventListener(
    _type: 'message',
    listener: (event: {data: unknown}) => void,
  ) {
    this.listeners.push(listener);
  }
  removeEventListener(
    _type: 'message',
    listener: (event: {data: unknown}) => void,
  ) {
    this.listeners = this.listeners.filter(entry => entry !== listener);
  }
  emit(data: string) {
    for (const listener of this.listeners) listener({data});
  }
}

class FakePeerConnection {
  iceGatheringState = 'complete';
  localDescription: {type?: string; sdp?: string} | null = {
    type: 'offer',
    sdp: 'offer-sdp',
  };
  remote: {type: 'answer'; sdp: string} | null = null;
  dataChannel = new FakeDataChannel();
  tracks: unknown[] = [];
  closed = false;
  private listeners: Record<string, Array<(...args: unknown[]) => void>> = {};
  addTrack(track: unknown) {
    this.tracks.push(track);
  }
  createDataChannel() {
    return this.dataChannel;
  }
  async createOffer() {
    return {type: 'offer', sdp: 'offer-sdp'};
  }
  async setLocalDescription() {}
  async setRemoteDescription(description: {type: 'answer'; sdp: string}) {
    this.remote = description;
  }
  addEventListener(type: string, listener: (...args: unknown[]) => void) {
    (this.listeners[type] ??= []).push(listener);
  }
  removeEventListener(type: string, listener: (...args: unknown[]) => void) {
    this.listeners[type] = (this.listeners[type] ?? []).filter(
      entry => entry !== listener,
    );
  }
  close() {
    this.closed = true;
  }
}

type FakeMicrophone = {
  getAudioTracks(): Array<{stopped: boolean; stop(): void}>;
  getTracks(): Array<{stopped: boolean; stop(): void}>;
};

function makeScope(getUserMedia?: () => Promise<FakeMicrophone>) {
  const peer = new FakePeerConnection();
  const track = {
    stopped: false,
    stop() {
      track.stopped = true;
    },
  };
  const microphone: FakeMicrophone = {
    getAudioTracks: () => [track],
    getTracks: () => [track],
  };
  const audio = {
    autoplay: false,
    srcObject: null as unknown,
    play: async () => undefined,
    pause: () => undefined,
  };
  const scope = {
    RTCPeerConnection: function () {
      return peer;
    },
    navigator: {
      mediaDevices: {
        getUserMedia: getUserMedia ?? (async () => microphone),
      },
    },
    Audio: function () {
      return audio;
    },
    MediaStream: function (tracks: unknown[]) {
      return {tracks};
    },
  } as unknown as LiveWebRtcScope;
  return {scope, peer, track};
}

test('exchanges the SDP offer and follows the data channel lifecycle', async () => {
  const {scope, peer, track} = makeScope();
  const phases: LiveVoicePhase[] = [];
  const offers: string[] = [];
  const session = new LiveWebRtcSession(
    scope,
    async sdp => {
      offers.push(sdp);
      return {
        provider: 'gpt_live',
        sessionId: 'live_test',
        answerSdp: 'answer-sdp',
      };
    },
    {onPhase: phase => phases.push(phase)},
  );
  await session.start();
  expect(offers).toEqual(['offer-sdp']);
  expect(peer.remote).toEqual({type: 'answer', sdp: 'answer-sdp'});
  expect(peer.tracks).toHaveLength(1);
  expect(phases).toContain('connecting');
  peer.dataChannel.emit(JSON.stringify({type: 'session.started'}));
  expect(phases).toContain('live');

  session.stop();
  expect(peer.dataChannel.sent).toEqual([
    JSON.stringify({type: 'session.close'}),
  ]);
  peer.dataChannel.emit(JSON.stringify({type: 'session.closed'}));
  expect(phases).toContain('closed');
  expect(peer.closed).toBe(true);
  expect(track.stopped).toBe(true);
  expect(peer.dataChannel.closed).toBe(true);
});

test('fails cleanly when microphone capture is rejected', async () => {
  const {scope, peer} = makeScope(async () => {
    throw new Error('NotAllowedError');
  });
  const phases: LiveVoicePhase[] = [];
  const session = new LiveWebRtcSession(
    scope,
    async () => ({
      provider: 'gpt_live' as const,
      sessionId: 'live_test',
      answerSdp: 'answer-sdp',
    }),
    {onPhase: phase => phases.push(phase)},
  );
  await session.start();
  expect(phases).toContain('error');
  expect(peer.closed).toBe(true);
});

test('resolveLiveWebRtcScope stays null without a peer connection', () => {
  const scope = globalThis as {
    RTCPeerConnection?: unknown;
    navigator?: {mediaDevices?: {getUserMedia?: unknown}};
  };
  const previousPeer = scope.RTCPeerConnection;
  const previousMedia = scope.navigator?.mediaDevices;
  try {
    delete scope.RTCPeerConnection;
    expect(resolveLiveWebRtcScope()).toBeNull();
    scope.RTCPeerConnection = class {};
    scope.navigator = {mediaDevices: {getUserMedia: () => undefined}};
    expect(resolveLiveWebRtcScope()).not.toBeNull();
  } finally {
    if (previousPeer === undefined) {
      delete scope.RTCPeerConnection;
    } else {
      scope.RTCPeerConnection = previousPeer;
    }
    if (previousMedia === undefined) {
      delete scope.navigator;
    }
  }
});
