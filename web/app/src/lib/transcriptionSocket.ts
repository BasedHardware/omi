/**
 * WebSocket client for real-time transcription.
 * Connects to the Omi transcription API and streams audio data.
 */

import { getIdToken, auth } from './firebase';

export interface TranscriptSegment {
  id: string;
  text: string;
  speaker: number;
  isUser: boolean;
  timestamp: number;
}

export interface TranscriptionSocketOptions {
  language?: string;
  sampleRate?: number;
  onSegment: (segment: TranscriptSegment) => void;
  onError: (error: string) => void;
  onConnected: () => void;
  onDisconnected: () => void;
}

type ConnectionState = 'disconnected' | 'connecting' | 'connected';

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_BASE_URL || 'wss://api.omi.me';

export class TranscriptionSocket {
  private ws: WebSocket | null = null;
  private options: TranscriptionSocketOptions;
  private state: ConnectionState = 'disconnected';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private audioBuffer: Int16Array[] = [];
  private isBuffering = false;

  constructor(options: TranscriptionSocketOptions) {
    this.options = {
      language: 'multi',
      sampleRate: 16000,
      ...options,
    };
  }

  async connect(): Promise<void> {
    if (this.state !== 'disconnected') {
      console.warn('TranscriptionSocket: Already connecting or connected');
      return;
    }

    this.state = 'connecting';

    try {
      const token = await getIdToken();
      if (!token) {
        throw new Error('Not authenticated');
      }

      const uid = auth.currentUser?.uid;
      if (!uid) {
        throw new Error('User ID not available');
      }

      // Build WebSocket URL with query parameters
      const params = new URLSearchParams({
        language: this.options.language || 'multi',
        sample_rate: String(this.options.sampleRate || 16000),
        codec: 'pcm16',
        uid: uid,
        token: token, // Pass Firebase token for web auth
        source: 'web',
        include_speech_profile: 'true',
      });

      const wsUrl = `${WS_BASE_URL}/v4/listen?${params.toString()}`;

      this.ws = new WebSocket(wsUrl);

      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        console.log('TranscriptionSocket: Connected');
        this.state = 'connected';
        this.reconnectAttempts = 0;
        this.options.onConnected();

        // Flush buffered audio
        if (this.audioBuffer.length > 0) {
          console.log(`TranscriptionSocket: Flushing ${this.audioBuffer.length} buffered chunks`);
          this.audioBuffer.forEach((chunk) => this.sendAudio(chunk));
          this.audioBuffer = [];
        }
        this.isBuffering = false;
      };

      this.ws.onmessage = (event) => {
        this.handleMessage(event);
      };

      this.ws.onerror = (event) => {
        console.error('TranscriptionSocket: Error', event);
      };

      this.ws.onclose = (event) => {
        console.log('TranscriptionSocket: Closed', event.code, event.reason);
        this.state = 'disconnected';
        this.ws = null;
        this.options.onDisconnected();

        // Auto-reconnect on unexpected close
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          console.log(
            `TranscriptionSocket: Reconnecting (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
          );
          this.isBuffering = true;
          setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
        }
      };
    } catch (err) {
      this.state = 'disconnected';
      const message = err instanceof Error ? err.message : 'Failed to connect';
      this.options.onError(message);
      throw err;
    }
  }

  private handleMessage(event: MessageEvent): void {
    try {
      // Handle text messages (JSON)
      if (typeof event.data === 'string') {
        const data = JSON.parse(event.data);

        // Handle segment array
        if (Array.isArray(data)) {
          data.forEach((segmentData) => {
            const segment: TranscriptSegment = {
              id: segmentData.id || `seg-${Date.now()}-${Math.random()}`,
              text: segmentData.text || '',
              speaker: segmentData.speakerId || segmentData.speaker || 0,
              isUser: segmentData.isUser ?? segmentData.is_user ?? false,
              timestamp: Date.now(),
            };

            if (segment.text.trim()) {
              this.options.onSegment(segment);
            }
          });
        }
        // Handle single segment object
        else if (data.text) {
          const segment: TranscriptSegment = {
            id: data.id || `seg-${Date.now()}-${Math.random()}`,
            text: data.text,
            speaker: data.speakerId || data.speaker || 0,
            isUser: data.isUser ?? data.is_user ?? false,
            timestamp: Date.now(),
          };

          if (segment.text.trim()) {
            this.options.onSegment(segment);
          }
        }
        // Handle event messages
        else if (data.type) {
          console.log('TranscriptionSocket: Event', data.type, data);
        }
      }
      // Handle binary messages (shouldn't happen, but log if they do)
      else if (event.data instanceof ArrayBuffer) {
        console.log('TranscriptionSocket: Received binary data', event.data.byteLength);
      }
    } catch (err) {
      console.error('TranscriptionSocket: Failed to parse message', err);
    }
  }

  sendAudio(pcmData: Int16Array): void {
    // Buffer if not connected yet
    if (this.isBuffering || this.state !== 'connected' || !this.ws) {
      this.audioBuffer.push(pcmData);
      // Limit buffer size to prevent memory issues
      if (this.audioBuffer.length > 100) {
        this.audioBuffer.shift();
      }
      return;
    }

    try {
      // Send as binary
      this.ws.send(pcmData.buffer);
    } catch (err) {
      console.error('TranscriptionSocket: Failed to send audio', err);
    }
  }

  disconnect(): void {
    this.isBuffering = false;
    this.audioBuffer = [];
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect

    if (this.ws) {
      this.ws.close(1000, 'User stopped recording');
      this.ws = null;
    }

    this.state = 'disconnected';
  }

  isConnected(): boolean {
    return this.state === 'connected';
  }
}

/**
 * Create a new transcription socket instance
 */
export function createTranscriptionSocket(
  options: TranscriptionSocketOptions
): TranscriptionSocket {
  return new TranscriptionSocket(options);
}
