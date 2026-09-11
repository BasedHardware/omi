import {LiveUnsupportedError, type LiveSession} from './liveClient';

// Browser/WebRTC runtime for GPT-Live-1. React Native native platforms do not
// ship an RTCPeerConnection, so this module resolves a scope and reports
// LiveUnsupportedError instead of pretending a call started. PWA/web gets the
// full duplex audio path.
export type LiveVoicePhase =
  | 'idle'
  | 'connecting'
  | 'live'
  | 'stopping'
  | 'closed'
  | 'error';

export type LiveVoiceCallbacks = {
  onPhase?: (phase: LiveVoicePhase, detail?: string) => void;
  onSessionId?: (sessionId: string) => void;
  onEvent?: (event: unknown) => void;
};

type LiveMediaTrack = {stop(): void};
type LiveMediaStream = {
  getAudioTracks(): LiveMediaTrack[];
  getTracks(): LiveMediaTrack[];
};
type LiveDataChannel = {
  readyState: string;
  send(data: string): void;
  close(): void;
  addEventListener(
    type: 'message',
    listener: (event: {data: unknown}) => void,
  ): void;
  removeEventListener(
    type: 'message',
    listener: (event: {data: unknown}) => void,
  ): void;
};
type LiveRemoteTrackEvent = {track?: unknown; streams?: unknown[]};
type LiveAudioElement = {
  autoplay: boolean;
  srcObject: unknown;
  play?: () => Promise<void>;
  pause?: () => void;
};
type LiveIceEvent = (...args: unknown[]) => void;
type LivePeerConnection = {
  iceGatheringState: string;
  localDescription: {type?: string; sdp?: string} | null;
  addTrack(track: unknown, stream: unknown): void;
  createDataChannel(label: string): LiveDataChannel;
  createOffer(): Promise<{type: string; sdp?: string}>;
  setLocalDescription(description: {type: string; sdp?: string}): Promise<void>;
  setRemoteDescription(description: {
    type: 'answer';
    sdp: string;
  }): Promise<void>;
  addEventListener(type: string, listener: LiveIceEvent): void;
  removeEventListener(type: string, listener: LiveIceEvent): void;
  close(): void;
};

export type LiveWebRtcScope = {
  RTCPeerConnection: new () => LivePeerConnection;
  navigator?: {
    mediaDevices?: {
      getUserMedia(constraints: {audio: boolean}): Promise<LiveMediaStream>;
    };
  };
  Audio?: new () => LiveAudioElement;
  MediaStream?: new (tracks: unknown[]) => unknown;
};

export function resolveLiveWebRtcScope(): LiveWebRtcScope | null {
  const scope = globalThis as unknown as Partial<LiveWebRtcScope>;
  if (typeof scope.RTCPeerConnection !== 'function') {
    return null;
  }
  if (typeof scope.navigator?.mediaDevices?.getUserMedia !== 'function') {
    return null;
  }
  return scope as LiveWebRtcScope;
}

export class LiveWebRtcSession {
  private peer: LivePeerConnection | null = null;
  private events: LiveDataChannel | null = null;
  private microphone: LiveMediaStream | null = null;
  private audio: LiveAudioElement | null = null;
  private closeTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(
    private readonly scope: LiveWebRtcScope,
    private readonly requestAnswer: (sdp: string) => Promise<LiveSession>,
    private readonly callbacks: LiveVoiceCallbacks = {},
  ) {}

  async start(): Promise<void> {
    if (this.closed) return;
    this.callbacks.onPhase?.('connecting');
    try {
      const peer = new this.scope.RTCPeerConnection();
      this.peer = peer;
      peer.addEventListener('track', (...args: unknown[]) => {
        this.attachRemoteAudio(args[0] as LiveRemoteTrackEvent);
      });
      const mediaDevices = this.scope.navigator?.mediaDevices;
      if (mediaDevices === undefined) {
        throw new LiveUnsupportedError();
      }
      const microphone = await mediaDevices.getUserMedia({audio: true});
      if (this.closed) {
        for (const track of microphone.getTracks()) track.stop();
        return;
      }
      this.microphone = microphone;
      for (const track of microphone.getAudioTracks()) {
        peer.addTrack(track, microphone);
      }
      const events = peer.createDataChannel('oai-events');
      this.events = events;
      events.addEventListener('message', event => this.handleEvent(event));
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      await this.waitForIce(peer);
      const sdp = peer.localDescription?.sdp;
      if (typeof sdp !== 'string' || sdp.length === 0) {
        throw new Error('Missing local SDP offer');
      }
      const session = await this.requestAnswer(sdp);
      if (this.closed) return;
      this.callbacks.onSessionId?.(session.sessionId);
      await peer.setRemoteDescription({
        type: 'answer',
        sdp: session.answerSdp,
      });
      // The HTTP request already started the session. The data channel emits
      // session.started next; only then is the conversation truly live.
    } catch (error) {
      if (!this.closed) this.callbacks.onPhase?.('error', detail(error));
      this.dispose();
    }
  }

  stop(): void {
    if (this.closed) return;
    const events = this.events;
    if (events !== null && events.readyState === 'open') {
      try {
        events.send(JSON.stringify({type: 'session.close'}));
      } catch {}
      this.callbacks.onPhase?.('stopping');
      // Keep media and the event channel alive while pending work drains; the
      // session.closed event finalizes first, and this timeout is the backstop.
      this.closeTimer = setTimeout(() => {
        this.callbacks.onPhase?.('closed');
        this.dispose();
      }, 15_000);
      return;
    }
    this.callbacks.onPhase?.('closed');
    this.dispose();
  }

  private handleEvent(event: {data: unknown}): void {
    if (typeof event.data !== 'string') return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(event.data);
    } catch {
      return;
    }
    if (parsed === null || typeof parsed !== 'object') return;
    const type = (parsed as {type?: unknown}).type;
    if (type === 'session.started') {
      this.callbacks.onPhase?.('live');
    } else if (type === 'session.closed') {
      this.callbacks.onPhase?.('closed');
      this.dispose();
      return;
    }
    this.callbacks.onEvent?.(parsed);
  }

  private attachRemoteAudio(event: LiveRemoteTrackEvent): void {
    const AudioCtor = this.scope.Audio;
    if (AudioCtor === undefined || this.audio !== null) return;
    const audio = new AudioCtor();
    audio.autoplay = true;
    const streams = event.streams;
    if (Array.isArray(streams) && streams.length > 0) {
      audio.srcObject = streams[0];
    } else if (
      event.track !== undefined &&
      this.scope.MediaStream !== undefined
    ) {
      audio.srcObject = new this.scope.MediaStream([event.track]);
    }
    this.audio = audio;
    void audio.play?.().catch(() => undefined);
  }

  private waitForIce(peer: LivePeerConnection): Promise<void> {
    if (peer.iceGatheringState === 'complete') {
      return Promise.resolve();
    }
    return new Promise(resolve => {
      const timeout = setTimeout(() => {
        peer.removeEventListener('icegatheringstatechange', onState);
        resolve();
      }, 10_000);
      const onState = (...args: unknown[]) => {
        void args;
        if (peer.iceGatheringState !== 'complete') return;
        clearTimeout(timeout);
        peer.removeEventListener('icegatheringstatechange', onState);
        resolve();
      };
      peer.addEventListener('icegatheringstatechange', onState);
    });
  }

  private dispose(): void {
    if (this.closed) return;
    this.closed = true;
    if (this.closeTimer !== null) {
      clearTimeout(this.closeTimer);
      this.closeTimer = null;
    }
    const events = this.events;
    this.events = null;
    if (events !== null) {
      try {
        events.close();
      } catch {}
    }
    const microphone = this.microphone;
    this.microphone = null;
    if (microphone !== null) {
      for (const track of microphone.getTracks()) track.stop();
    }
    const audio = this.audio;
    this.audio = null;
    if (audio !== null) {
      audio.pause?.();
      audio.srcObject = null;
    }
    const peer = this.peer;
    this.peer = null;
    if (peer !== null) {
      try {
        peer.close();
      } catch {}
    }
  }
}

function detail(error: unknown): string {
  return error instanceof Error && error.message.length > 0
    ? error.message
    : 'Live voice failed';
}
