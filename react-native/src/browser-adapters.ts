export type BluetoothDeviceLike = {
  name?: string | null;
};

export type BluetoothLike = {
  requestDevice(options: {
    acceptAllDevices: boolean;
  }): Promise<BluetoothDeviceLike>;
};

export type MediaStreamTrackLike = {
  stop(): void;
};

export type MediaStreamLike = {
  getTracks(): readonly MediaStreamTrackLike[];
};

export type MediaDevicesLike = {
  getUserMedia(constraints: {audio: boolean}): Promise<MediaStreamLike>;
};

export type PermissionsLike = {
  query(descriptor: {name: 'microphone'}): Promise<{
    state: 'granted' | 'denied' | 'prompt';
  }>;
};

export type BrowserEnvironment = {
  bluetooth?: BluetoothLike;
  mediaDevices?: MediaDevicesLike;
  permissions?: PermissionsLike;
};

export type BrowserCapabilitySnapshot = {
  bluetooth: 'unsupported' | 'available' | 'selected' | 'denied' | 'error';
  bluetoothDeviceName: string | null;
  microphone: 'unsupported' | 'not-requested' | 'granted' | 'denied' | 'error';
  omiCapture: 'unsupported' | 'not-wired';
};

export type BrowserCapabilityResult =
  | {ok: true; deviceName: string | null}
  | {ok: false; reason: 'unsupported' | 'cancelled' | 'denied' | 'error'};

function defaultEnvironment(): BrowserEnvironment {
  if (typeof navigator === 'undefined') {
    return {};
  }
  const browserNavigator = navigator as typeof navigator & {
    bluetooth?: BluetoothLike;
    mediaDevices?: MediaDevicesLike;
    permissions?: PermissionsLike;
  };
  return {
    bluetooth: browserNavigator.bluetooth,
    mediaDevices: browserNavigator.mediaDevices,
    permissions: browserNavigator.permissions,
  };
}

function errorName(error: unknown): string {
  return error instanceof DOMException ? error.name : '';
}

export function createBrowserCapabilityAdapter(
  environment = defaultEnvironment(),
) {
  const state: BrowserCapabilitySnapshot = {
    bluetooth:
      environment.bluetooth === undefined ? 'unsupported' : 'available',
    bluetoothDeviceName: null,
    microphone:
      environment.mediaDevices?.getUserMedia === undefined
        ? 'unsupported'
        : 'not-requested',
    omiCapture:
      environment.mediaDevices?.getUserMedia === undefined
        ? 'unsupported'
        : 'not-wired',
  };

  return {
    snapshot(): BrowserCapabilitySnapshot {
      return {...state};
    },
    async refresh(): Promise<BrowserCapabilitySnapshot> {
      if (
        environment.permissions !== undefined &&
        state.microphone !== 'unsupported'
      ) {
        try {
          const permission = await environment.permissions.query({
            name: 'microphone',
          });
          state.microphone =
            permission.state === 'prompt' ? 'not-requested' : permission.state;
        } catch {
          state.microphone = 'not-requested';
        }
      }
      return {...state};
    },
    async chooseBluetoothDevice(): Promise<BrowserCapabilityResult> {
      if (environment.bluetooth === undefined) {
        return {ok: false, reason: 'unsupported'};
      }
      try {
        const device = await environment.bluetooth.requestDevice({
          acceptAllDevices: true,
        });
        const deviceName = device.name?.trim() || null;
        state.bluetooth = 'selected';
        state.bluetoothDeviceName = deviceName;
        return {ok: true, deviceName};
      } catch (error) {
        const name = errorName(error);
        const reason =
          name === 'NotFoundError'
            ? 'cancelled'
            : name === 'NotAllowedError'
            ? 'denied'
            : 'error';
        if (reason === 'denied') {
          state.bluetooth = 'denied';
        }
        if (reason === 'error') {
          state.bluetooth = 'error';
        }
        return {ok: false, reason};
      }
    },
    async checkMicrophone(): Promise<BrowserCapabilityResult> {
      if (environment.mediaDevices?.getUserMedia === undefined) {
        return {ok: false, reason: 'unsupported'};
      }
      try {
        const stream = await environment.mediaDevices.getUserMedia({
          audio: true,
        });
        stream.getTracks().forEach(track => track.stop());
        state.microphone = 'granted';
        return {ok: true, deviceName: null};
      } catch (error) {
        const reason =
          errorName(error) === 'NotAllowedError' ? 'denied' : 'error';
        state.microphone = reason === 'denied' ? 'denied' : 'error';
        return {ok: false, reason};
      }
    },
  };
}
