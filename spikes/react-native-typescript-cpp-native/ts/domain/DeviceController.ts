import type { INativePacketBoundary } from '../contracts/NativeBoundaryContract.ts';
import { FakeDeviceTransport } from '../transport/FakeDeviceTransport.ts';
import type { TransportEvent } from '../transport/FakeDeviceTransport.ts';

export interface DeviceState {
  id: string;
  name: string;
  type: 'headset' | 'glasses';
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  validPacketCount: number;
  corruptPacketCount: number;
  lastChecksum?: number;
  retryCount: number;
}

export type DeviceStateListener = (devices: DeviceState[]) => void;

export class DeviceController {
  private transport: FakeDeviceTransport;
  private nativeBoundary: INativePacketBoundary;
  private deviceStates: Map<string, DeviceState> = new Map();
  private listeners: Set<DeviceStateListener> = new Set();
  private unsubscribeTransport?: () => void;

  constructor(
    transport: FakeDeviceTransport,
    nativeBoundary: INativePacketBoundary
  ) {
    this.transport = transport;
    this.nativeBoundary = nativeBoundary;

    this.syncFromTransport();
    this.unsubscribeTransport = this.transport.subscribe(event => this.handleTransportEvent(event));
  }

  getDevices(): DeviceState[] {
    return Array.from(this.deviceStates.values()).map(s => ({ ...s }));
  }

  connectDevice(deviceId: string): boolean {
    const dev = this.deviceStates.get(deviceId);
    if (!dev) return false;

    dev.status = 'connecting';
    this.notifyListeners();

    const success = this.transport.connect(deviceId);
    if (!success) {
      dev.status = 'error';
      this.notifyListeners();
    }
    return success;
  }

  disconnectDevice(deviceId: string): boolean {
    const dev = this.deviceStates.get(deviceId);
    if (!dev) return false;

    const success = this.transport.disconnect(deviceId);
    if (success) {
      dev.status = 'disconnected';
      this.notifyListeners();
    }
    return success;
  }

  receivePacket(deviceId: string, rawData: Uint8Array): void {
    const dev = this.deviceStates.get(deviceId);
    if (!dev) return;

    const result = this.nativeBoundary.normalizePacket(rawData);
    if (result.status === 'SUCCESS') {
      dev.validPacketCount += 1;
      dev.lastChecksum = result.checksum;
    } else {
      dev.corruptPacketCount += 1;
    }
    this.notifyListeners();
  }

  subscribe(listener: DeviceStateListener): () => void {
    this.listeners.add(listener);
    listener(this.getDevices());
    return () => {
      this.listeners.delete(listener);
    };
  }

  destroy(): void {
    if (this.unsubscribeTransport) {
      this.unsubscribeTransport();
    }
  }

  private syncFromTransport(): void {
    const transportDevs = this.transport.getDevices();
    for (const td of transportDevs) {
      const existing = this.deviceStates.get(td.id);
      this.deviceStates.set(td.id, {
        id: td.id,
        name: td.name,
        type: td.type,
        status: td.connected ? 'connected' : 'disconnected',
        validPacketCount: existing ? existing.validPacketCount : 0,
        corruptPacketCount: existing ? existing.corruptPacketCount : 0,
        lastChecksum: existing ? existing.lastChecksum : undefined,
        retryCount: td.retryCount,
      });
    }
  }

  private handleTransportEvent(event: TransportEvent): void {
    const dev = this.deviceStates.get(event.deviceId);
    if (!dev) return;

    switch (event.type) {
      case 'device_connected':
        dev.status = 'connected';
        dev.retryCount = 0;
        break;
      case 'device_disconnected':
        dev.status = 'disconnected';
        break;
      case 'retry_attempted':
        dev.status = 'connecting';
        dev.retryCount = event.attempt || dev.retryCount;
        break;
      case 'retry_exhausted':
        dev.status = 'error';
        break;
      case 'packet_received':
        if (event.packet) {
          this.receivePacket(event.deviceId, event.packet.data);
          return;
        }
        break;
    }
    this.notifyListeners();
  }

  private notifyListeners(): void {
    const snapshot = this.getDevices();
    for (const listener of this.listeners) {
      listener(snapshot);
    }
  }
}
