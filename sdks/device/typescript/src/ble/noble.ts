// Keep UUIDs local to avoid circular import with ../index → ./ble.
const OMI_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214';
const AUDIO_DATA_UUID = '19b10001-e8f2-537e-4f6c-d104768a1214';

export type ScannedDevice = { id: string; name: string; rssi: number };

type NobleLike = {
  waitForPoweredOnAsync?: (timeout?: number) => Promise<void>;
  startScanningAsync: (serviceUUIDs?: string[], allowDuplicates?: boolean) => Promise<void>;
  stopScanningAsync: () => Promise<void>;
  connectAsync?: (idOrAddress: string) => Promise<any>;
  on: (event: string, listener: (...args: any[]) => void) => void;
  removeListener: (event: string, listener: (...args: any[]) => void) => void;
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
  // Own one event subscription and one deadline. Waiting for the next item of
  // discoverAsync() cannot enforce a deadline when the adapter is quiet.
  const onDiscover = (peripheral: any) => {
    const id = String(peripheral.id || peripheral.address || '');
    if (!id) return;
    byId.set(id, {
      id,
      name: String(peripheral.advertisement?.localName || peripheral.advertisement?.name || ''),
      rssi: Number(peripheral.rssi ?? 0) || 0,
    });
  };
  let active = false;
  let restart: Promise<void> = Promise.resolve();
  let failScan: (error: unknown) => void = () => {};
  const scanFailure = new Promise<never>((_, reject) => { failScan = reject; });
  const onScanStop = () => {
    if (!active || noble.state !== 'poweredOn') return;
    // Bindings can pause discovery while connecting. Serialize resumes and
    // recheck ownership so a queued resume cannot outlive this scan window.
    restart = restart.then(async () => {
      if (active && noble.state === 'poweredOn') await noble.startScanningAsync([], false);
    });
    void restart.catch(failScan);
  };
  noble.on('discover', onDiscover);
  noble.on('scanStop', onScanStop);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await noble.startScanningAsync([], false);
    active = true;
    await Promise.race([
      new Promise<void>((resolve) => { timer = setTimeout(resolve, Math.max(0, timeoutMs)); }),
      scanFailure,
    ]);
  } finally {
    active = false;
    clearTimeout(timer);
    noble.removeListener('discover', onDiscover);
    noble.removeListener('scanStop', onScanStop);
    try {
      await restart;
    } finally {
      await noble.stopScanningAsync();
    }
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
