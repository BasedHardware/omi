export type OmiDevice = { id: string; name: string; rssi: number; source?: string };
export type BluetoothState = {
  available?: boolean;
  enabled?: boolean;
  scan?: boolean;
  scanActive?: boolean;
  connection?: string;
  state?: string;
  implementation?: string;
  lastError?: string | null;
};

type OmiNativeApi = {
  getNativeCapabilities?: () => string;
  normalizePacket?: (rawBase64: string) => string;
  getBluetoothState?: () => string;
  startOmiScan?: () => string;
  stopOmiScan?: () => string;
  getOmiScanResults?: () => string;
  connectOmi?: (id: string) => string;
  disconnectOmi?: () => string;
};

export const NATIVE_ADAPTER_UNAVAILABLE = 'NATIVE_ADAPTER_UNAVAILABLE';

function native(): OmiNativeApi | undefined {
  if (typeof NativeModules === 'undefined') return undefined;
  return (NativeModules as { OmiNativeModule?: OmiNativeApi }).OmiNativeModule;
}

function parse<T>(raw: string | undefined, fallback: T): T {
  if (!raw || raw === NATIVE_ADAPTER_UNAVAILABLE) return fallback;
  try { return JSON.parse(raw) as T; } catch { return fallback; }
}

export function getNativeCapabilities(): string {
  return native()?.getNativeCapabilities?.() ?? NATIVE_ADAPTER_UNAVAILABLE;
}

export function normalizePacket(rawBase64: string): string {
  return native()?.normalizePacket?.(rawBase64) ?? NATIVE_ADAPTER_UNAVAILABLE;
}

export function getBluetoothState(): BluetoothState {
  return parse(native()?.getBluetoothState?.(), { available: false, implementation: 'unavailable' });
}

export function startOmiScan(): BluetoothState {
  return parse(native()?.startOmiScan?.(), { available: false, lastError: NATIVE_ADAPTER_UNAVAILABLE });
}

export function stopOmiScan(): BluetoothState {
  return parse(native()?.stopOmiScan?.(), { available: false, lastError: NATIVE_ADAPTER_UNAVAILABLE });
}

export function getOmiScanResults(): OmiDevice[] {
  return parse(native()?.getOmiScanResults?.(), []);
}

export function connectOmi(id: string): BluetoothState {
  return parse(native()?.connectOmi?.(id), { available: false, lastError: NATIVE_ADAPTER_UNAVAILABLE });
}

export function disconnectOmi(): BluetoothState {
  return parse(native()?.disconnectOmi?.(), { available: false, lastError: NATIVE_ADAPTER_UNAVAILABLE });
}
