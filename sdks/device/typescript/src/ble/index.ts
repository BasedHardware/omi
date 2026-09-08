import { connectAndListen, requireNoble, scanForDevices, type ScannedDevice } from './noble';

export { connectAndListen, scanForDevices, requireNoble, NOBLE_MISSING } from './noble';
export type { ScannedDevice } from './noble';

// Local shapes mirror ../index BleTransport without importing it (cycle).
type AudioPacketHandler = (packet: Uint8Array) => void;
type BleTransport = {
  startAudioNotifications(handler: AudioPacketHandler): Promise<void> | void;
  stopAudioNotifications?(): Promise<void> | void;
};

/**
 * Build a BleTransport backed by optional `@stoprocent/noble`.
 * Throws a clear install hint if noble is not available.
 */
export async function createNobleTransport(deviceId: string): Promise<BleTransport> {
  await requireNoble();

  let session: { disconnect(): Promise<void> } | null = null;

  return {
    async startAudioNotifications(handler: AudioPacketHandler) {
      if (session) {
        await session.disconnect();
        session = null;
      }
      session = await connectAndListen(deviceId, handler);
    },
    async stopAudioNotifications() {
      if (!session) return;
      const s = session;
      session = null;
      await s.disconnect();
    },
  };
}

/** Convenience: scan then return first named Omi-ish device, or first result. */
export async function findFirstDevice(timeoutMs = 5000): Promise<ScannedDevice | null> {
  const devices = await scanForDevices(timeoutMs);
  return (
    devices.find((d) => /omi|friend/i.test(d.name)) ??
    devices.find((d) => d.name) ??
    devices[0] ??
    null
  );
}
