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
  private connectionTimeout: ReturnType<typeof setTimeout> | null = null;
  private tokenRefreshInterval: ReturnType<typeof setInterval> | null = null;
  private isRefreshing = false; // Flag to indicate token refresh in progress
  private isAuthenticated = false; // Flag to indicate WebSocket auth completed
  private pendingToken: string | null = null; // Token for first-message auth
  private static readonly CONNECTION_TIMEOUT_MS = 15000; // 15 seconds
  private static readonly TOKEN_REFRESH_INTERVAL_MS = 50 * 60 * 1000; // 50 minutes (tokens expire at 60 min)

  constructor(options: TranscriptionSocketOptions) {
    this.options = {
      language: 'multi',
      sampleRate: 16000,
      ...options,
    };
  }

  private clearConnectionTimeout(): void {
    if (this.connectionTimeout) {
      clearTimeout(this.connectionTimeout);
      this.connectionTimeout = null;
    }
  }

  private startTokenRefresh(): void {
    // Clear any existing interval
    this.stopTokenRefresh();

    // Set up periodic token refresh to handle long recordings
    this.tokenRefreshInterval = setInterval(() => {
      this.refreshConnection();
    }, TranscriptionSocket.TOKEN_REFRESH_INTERVAL_MS);
  }

  private stopTokenRefresh(): void {
    if (this.tokenRefreshInterval) {
      clearInterval(this.tokenRefreshInterval);
      this.tokenRefreshInterval = null;
    }
  }

  /**
   * Reconnect with a fresh token to handle token expiration for long recordings.
   * This gracefully closes the current connection and opens a new one.
   * The refresh is seamless - audio is buffered during the brief reconnection.
   */
  private async refreshConnection(): Promise<void> {
    if (this.state !== 'connected') {
      return;
    }

    // Set refreshing flag to prevent onDisconnected callback during refresh
    this.isRefreshing = true;

    // Buffer audio during reconnection
    this.isBuffering = true;

    // Close current connection gracefully
    if (this.ws) {
      this.ws.close(1000, 'Token refresh');
      this.ws = null;
    }

    this.state = 'disconnected';
    this.isAuthenticated = false;

    // Small delay to ensure clean disconnect
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Reconnect with fresh token
    try {
      await this.connect();
    } catch (err) {
      console.error('TranscriptionSocket: Failed to refresh connection', err);
      this.isRefreshing = false;
      this.options.onError('Failed to refresh connection - please restart recording');
    }
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

      // Build WebSocket URL with query parameters (auth via first message)
      const params = new URLSearchParams({
        language: this.options.language || 'multi',
        sample_rate: String(this.options.sampleRate || 16000),
        codec: 'pcm16',
        uid: uid,
        source: 'web',
        include_speech_profile: 'true',
      });

      // Store token for first-message auth
      this.pendingToken = token;

      const wsUrl = `${WS_BASE_URL}/v4/web/listen?${params.toString()}`;

      this.ws = new WebSocket(wsUrl);

      this.ws.binaryType = 'arraybuffer';

      // Set connection timeout
      this.connectionTimeout = setTimeout(() => {
        if (this.state === 'connecting') {
          console.error('TranscriptionSocket: Connection timeout');
          this.ws?.close();
          this.ws = null;
          this.state = 'disconnected';
          this.options.onError('Connection timeout - server unreachable');
        }
      }, TranscriptionSocket.CONNECTION_TIMEOUT_MS);

      this.ws.onopen = () => {
        this.clearConnectionTimeout();
        this.state = 'connected';

        // Send first-message authentication
        if (this.ws && this.pendingToken) {
          try {
            this.ws.send(JSON.stringify({ type: 'auth', token: this.pendingToken }));
          } catch (err) {
            console.error('TranscriptionSocket: Failed to send auth message, closing socket.', err);
            this.ws?.close();
          }
        }
        // Note: onConnected() and buffer flush happen after auth_response in handleMessage
      };

      this.ws.onmessage = (event) => {
        this.handleMessage(event);
      };

      this.ws.onerror = (event) => {
        this.clearConnectionTimeout();
        console.error('TranscriptionSocket: Error', event);
      };

      this.ws.onclose = (event) => {
        this.clearConnectionTimeout();
        this.state = 'disconnected';
        this.ws = null;

        // Don't call onDisconnected during token refresh - it's a seamless reconnection
        if (!this.isRefreshing) {
          this.options.onDisconnected();
        }

        // Auto-reconnect on unexpected close (but not during token refresh)
        if (!this.isRefreshing && event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          this.isBuffering = true;
          setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
        }
      };
    } catch (err) {
      this.clearConnectionTimeout();
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
        // Ignore keepalive ping messages
        if (event.data === 'ping') return;

        const data = JSON.parse(event.data);

        // Helper to parse speaker ID from various formats (e.g., "SPEAKER_01" -> 0, "1" -> 1)
        const parseSpeakerId = (id: string | number | undefined): number => {
          if (typeof id === 'number') return id;
          if (typeof id === 'string') {
            // Handle "SPEAKER_01" format - convert 1-indexed to 0-indexed
            const speakerMatch = id.match(/^SPEAKER_(\d+)$/);
            if (speakerMatch) return Math.max(0, parseInt(speakerMatch[1], 10) - 1);
            // Handle plain numeric strings (already 0-indexed)
            const num = parseInt(id, 10);
            if (!isNaN(num)) return num;
          }
          return 0;
        };

        // Handle segment array
        if (Array.isArray(data)) {
          data.forEach((segmentData) => {
            const segment: TranscriptSegment = {
              id: segmentData.id || `seg-${Date.now()}-${Math.random()}`,
              text: segmentData.text || '',
              speaker: parseSpeakerId(segmentData.speakerId ?? segmentData.speaker_id ?? segmentData.speaker),
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
            speaker: parseSpeakerId(data.speakerId ?? data.speaker_id ?? data.speaker),
            isUser: data.isUser ?? data.is_user ?? false,
            timestamp: Date.now(),
          };

          if (segment.text.trim()) {
            this.options.onSegment(segment);
          }
        }
        // Handle auth response (first-message authentication)
        else if (data.type === 'auth_response') {
          if (data.success) {
            this.isAuthenticated = true;
            this.pendingToken = null;
            this.reconnectAttempts = 0;
            this.isRefreshing = false;
            this.options.onConnected();

            // Start token refresh timer for long recordings
            this.startTokenRefresh();

            // Stop buffering and flush buffered audio
            this.isBuffering = false;
            if (this.audioBuffer.length > 0) {
              this.audioBuffer.forEach((chunk) => this.sendAudio(chunk));
              this.audioBuffer = [];
            }
          } else {
            console.error('TranscriptionSocket: Auth failed');
            this.options.onError('Authentication failed');
            this.ws?.close(1000, 'Auth failed');
          }
        }
        // Handle other event messages (silently ignore for now)
      }
    } catch (err) {
      console.error('TranscriptionSocket: Failed to parse message', err);
    }
  }

  sendAudio(pcmData: Int16Array): void {
    // Buffer if not connected or not authenticated yet
    if (this.isBuffering || this.state !== 'connected' || !this.ws || !this.isAuthenticated) {
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
    this.clearConnectionTimeout();
    this.stopTokenRefresh();
    this.isBuffering = false;
    this.isAuthenticated = false;
    this.pendingToken = null;
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
