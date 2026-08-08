export interface DeviceInfo {
  id: string;
  name: string;
  type: 'headset' | 'glasses';
  connected: boolean;
  retryCount: number;
}

export interface RawPacket {
  deviceId: string;
  seq: number;
  data: Uint8Array;
}

export type TransportEventType =
  | 'device_connected'
  | 'device_disconnected'
  | 'packet_received'
  | 'retry_attempted'
  | 'retry_exhausted';

export interface TransportEvent {
  type: TransportEventType;
  deviceId: string;
  packet?: RawPacket;
  attempt?: number;
  reason?: string;
}

export type TransportEventListener = (event: TransportEvent) => void;

export class FakeDeviceTransport {
  private devices: Map<string, DeviceInfo> = new Map();
  private listeners: Set<TransportEventListener> = new Set();
  private seqCounter: Map<string, number> = new Map();

  constructor() {
    // Initialize two simulated devices
    this.devices.set('dev-001', {
      id: 'dev-001',
      name: 'Omi Headset Alpha',
      type: 'headset',
      connected: false,
      retryCount: 0,
    });
    this.devices.set('dev-002', {
      id: 'dev-002',
      name: 'Omi Glass Beta',
      type: 'glasses',
      connected: false,
      retryCount: 0,
    });
    this.seqCounter.set('dev-001', 0);
    this.seqCounter.set('dev-002', 0);
  }

  getDevices(): DeviceInfo[] {
    return Array.from(this.devices.values()).map(dev => ({ ...dev }));
  }

  connect(deviceId: string): boolean {
    const dev = this.devices.get(deviceId);
    if (!dev) return false;
    dev.connected = true;
    dev.retryCount = 0;
    this.emit({ type: 'device_connected', deviceId });
    return true;
  }

  disconnect(deviceId: string): boolean {
    const dev = this.devices.get(deviceId);
    if (!dev) return false;
    dev.connected = false;
    this.emit({ type: 'device_disconnected', deviceId });
    return true;
  }

  sendPacket(deviceId: string, data: Uint8Array): boolean {
    const dev = this.devices.get(deviceId);
    if (!dev || !dev.connected) return false;

    const currentSeq = (this.seqCounter.get(deviceId) || 0) + 1;
    this.seqCounter.set(deviceId, currentSeq);

    const packet: RawPacket = {
      deviceId,
      seq: currentSeq,
      data: new Uint8Array(data),
    };

    this.emit({
      type: 'packet_received',
      deviceId,
      packet,
    });
    return true;
  }

  simulateRetry(deviceId: string, maxRetries: number): boolean {
    const dev = this.devices.get(deviceId);
    if (!dev) return false;

    if (maxRetries <= 0) {
      dev.connected = false;
      this.emit({
        type: 'retry_exhausted',
        deviceId,
        reason: 'Max retries limit reached',
      });
      return false;
    }

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      dev.retryCount = attempt;
      this.emit({
        type: 'retry_attempted',
        deviceId,
        attempt,
      });
    }

    dev.connected = true;
    this.emit({ type: 'device_connected', deviceId });
    return true;
  }

  subscribe(listener: TransportEventListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private emit(event: TransportEvent): void {
    for (const listener of this.listeners) {
      listener(event);
    }
  }
}
