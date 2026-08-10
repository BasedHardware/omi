export type OmiNativeApi = {
  getNativeCapabilities?: () => string;
  normalizePacket?: (rawBase64: string) => string;
};

export const NATIVE_ADAPTER_UNAVAILABLE = 'NATIVE_ADAPTER_UNAVAILABLE';

export function getOmiNative(): OmiNativeApi | undefined {
  if (typeof NativeModules === 'undefined') return undefined;
  return (NativeModules as { OmiNativeModule?: OmiNativeApi }).OmiNativeModule;
}

export function getNativeCapabilities(): string {
  return getOmiNative()?.getNativeCapabilities?.() ?? NATIVE_ADAPTER_UNAVAILABLE;
}

export function normalizePacket(rawBase64: string): string {
  return getOmiNative()?.normalizePacket?.(rawBase64) ?? NATIVE_ADAPTER_UNAVAILABLE;
}
