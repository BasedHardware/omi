// Keep UUIDs local to avoid circular import with ../index → ./ble.
const OMI_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214';
const AUDIO_DATA_UUID = '19b10001-e8f2-537e-4f6c-d104768a1214';

export type ScannedDevice = { id: string; name: string; rssi: number };

type NobleLike = {
  waitForPoweredOnAsync?: (timeout?: number) => Promise<void>;
  startScanningAsync: (serviceUUIDs?: string[], allowDuplicates?: boolean) => Promise<void>;
  stopScanningAsync: () => Promise<void>;
  discoverAsync?: () => AsyncGenerator<any, void, unknown>;
  connectAsync?: (idOrAddress: string) => Promise<any>;
  on?: (event: string, listener: (...args: any[]) => void) => void;
  removeListener?: (event: string, listener: (...args: any[]) => void) => void;
  state?: string;
  startScanning?: (serviceUUIDs?: string[], allowDuplicates?: boolean, cb?: (err?: Error) => void) => void;
  stopScanning?: (cb?: () => void) => void;
};

const NOBLE_MISSING =
  'Optional BLE dependency missing. Install with: bun add @stoprocent/noble (or npm i @stoprocent/noble)';

function asUuid(u: string): string {
  return u.toLowerCase().replace(/-/g, '');
}

async function loadNoble(): Promise<NobleLike> {
  try {
    const mod: any = await import('@stoprocent/noble');
    const noble: NobleLike = mod.default ?? mod.withBindings?.('default') ?? mod;
    if (!noble || typeof noble.startScanningAsync !== 'function') {
      throw new Error('invalid noble module shape');
    }
    return noble;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (/Cannot find module|ERR_MODULE_NOT_FOUND|Cannot find package/i.test(msg)) {
      throw new Error(NOBLE_MISSING);
    }
    // native binding failures still surface as missing optional BLE stack
    throw new Error(`${NOBLE_MISSING} (${msg})`);
  }
}

async function ensurePoweredOn(noble: NobleLike): Promise<void> {
  if (typeof noble.waitForPoweredOnAsync === 'function') {
    await noble.waitForPoweredOnAsync();
    return;
  }
  if (noble.state === 'poweredOn') return;
  await new Promise<void>((resolve, reject) => {
    const onState = (state: string) => {
      if (state === 'poweredOn') {
        noble.removeListener?.('stateChange', onState);
        resolve();
      }
    };
    noble.on?.('stateChange', onState);
    if (noble.state === 'poweredOn') {
      noble.removeListener?.('stateChange', onState);
      resolve();
      return;
    }
    setTimeout(() => {
      noble.removeListener?.('stateChange', onState);
      reject(new Error('BLE adapter did not reach poweredOn'));
    }, 15_000);
  });
}

/** Scan for nearby BLE peripherals. Requires optional `@stoprocent/noble`. */
export async function scanForDevices(timeoutMs = 5000): Promise<ScannedDevice[]> {
  const noble = await loadNoble();
  await ensurePoweredOn(noble);

  const byId = new Map<string, ScannedDevice>();
  const deadline = Date.now() + timeoutMs;

  await noble.startScanningAsync([], false);

  try {
    if (typeof noble.discoverAsync === 'function') {
      for await (const peripheral of noble.discoverAsync()) {
        const id = String(peripheral.id || peripheral.address || '');
        if (id) {
          byId.set(id, {
            id,
            name: String(peripheral.advertisement?.localName || peripheral.advertisement?.name || ''),
            rssi: Number(peripheral.rssi ?? 0) || 0,
          });
        }
        if (Date.now() >= deadline) break;
      }
    } else {
      await new Promise<void>((resolve) => {
        const onDiscover = (peripheral: any) => {
          const id = String(peripheral.id || peripheral.address || '');
          if (!id) return;
          byId.set(id, {
            id,
            name: String(peripheral.advertisement?.localName || ''),
            rssi: Number(peripheral.rssi ?? 0) || 0,
          });
        };
        noble.on?.('discover', onDiscover);
        const left = Math.max(0, deadline - Date.now());
        setTimeout(() => {
          noble.removeListener?.('discover', onDiscover);
          resolve();
        }, left);
      });
    }
  } finally {
    await noble.stopScanningAsync();
  }

  return [...byId.values()];
}

/**
 * Connect to device, subscribe to Omi audio notifications.
 * Returns a handle that disconnects and unsubscribes.
 */
export async function connectAndListen(
  deviceId: string,
  onPacket: (u8: Uint8Array) => void
): Promise<{ disconnect(): Promise<void> }> {
  const noble = await loadNoble();
  await ensurePoweredOn(noble);

  let peripheral: any;
  if (typeof noble.connectAsync === 'function') {
    peripheral = await noble.connectAsync(deviceId);
  } else {
    throw new Error('noble.connectAsync unavailable');
  }

  // Some bindings return already-connected peripheral; ensure connected.
  if (peripheral.state !== 'connected' && typeof peripheral.connectAsync === 'function') {
    await peripheral.connectAsync();
  }

  const wantService = asUuid(OMI_SERVICE_UUID);
  const wantChar = asUuid(AUDIO_DATA_UUID);

  let characteristics: any[] = [];
  if (typeof peripheral.discoverSomeServicesAndCharacteristicsAsync === 'function') {
    const found = await peripheral.discoverSomeServicesAndCharacteristicsAsync(
      [OMI_SERVICE_UUID],
      [AUDIO_DATA_UUID]
    );
    characteristics = found.characteristics ?? [];
  } else {
    const found = await peripheral.discoverAllServicesAndCharacteristicsAsync();
    characteristics = found.characteristics ?? [];
  }

  const audioChar =
    characteristics.find((c) => asUuid(String(c.uuid)) === wantChar) ??
    characteristics.find((c) => asUuid(String(c.uuid)).includes(wantChar.slice(0, 8)));

  if (!audioChar) {
    await peripheral.disconnectAsync?.();
    throw new Error(
      `Audio characteristic ${AUDIO_DATA_UUID} not found on ${deviceId} (service ${OMI_SERVICE_UUID})`
    );
  }

  // keep service uuid check soft — some stacks omit parent service on char
  void wantService;

  const onData = (data: ArrayBufferView | ArrayBuffer | number[]) => {
    const u8 =
      data instanceof Uint8Array
        ? data
        : ArrayBuffer.isView(data)
          ? new Uint8Array(data.buffer, data.byteOffset, data.byteLength)
          : data instanceof ArrayBuffer
            ? new Uint8Array(data)
            : new Uint8Array(data);
    onPacket(u8);
  };
  audioChar.on?.('data', onData);
  await audioChar.subscribeAsync();

  let closed = false;
  return {
    async disconnect() {
      if (closed) return;
      closed = true;
      try {
        audioChar.removeListener?.('data', onData);
        await audioChar.unsubscribeAsync?.();
      } catch {
        /* ignore */
      }
      try {
        await peripheral.disconnectAsync?.();
      } catch {
        /* ignore */
      }
    },
  };
}

/** Exposed for tests / fail-fast import check. */
export async function requireNoble(): Promise<NobleLike> {
  return loadNoble();
}

export { NOBLE_MISSING };
