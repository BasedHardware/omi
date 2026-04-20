import { create } from "zustand";

/**
 * Bluetooth device pairing store.
 *
 * Mirrors the shape of the Rust-side `DiscoveredDevice` event payload and
 * tracks per-device connection state so the Device Settings page can render
 * a live scan list without having to reconcile a blob of events itself.
 *
 * The store is populated by `services/bluetooth.ts`, which wires
 * `bluetooth://device-found` and `bluetooth://connection-state` events from
 * the Rust backend into plain Zustand mutations.
 */

export type ConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "failed";

export interface BluetoothDevice {
  id: string;
  name: string | null;
  rssi: number | null;
  address: string;
  /** Last observed connection status — defaults to `disconnected`. */
  status: ConnectionStatus;
  /** Populated when `status === "failed"` or when a connect attempt errors. */
  lastError?: string;
}

export interface ConnectedDeviceSummary {
  id: string;
  name: string | null;
  address: string;
}

interface DeviceState {
  /** Indexed by `id` so repeated `DeviceUpdated` events dedupe cleanly. */
  devices: Record<string, BluetoothDevice>;
  connected: ConnectedDeviceSummary[];
  isScanning: boolean;
  /**
   * Adapter-level error (e.g. Bluetooth off, permissions missing). Distinct
   * from per-device connection failures so the UI can surface an
   * actionable system-state banner.
   */
  error: string | null;

  setScanning: (scanning: boolean) => void;
  setError: (error: string | null) => void;
  upsertDevice: (
    partial: Pick<BluetoothDevice, "id" | "name" | "rssi" | "address">,
  ) => void;
  updateStatus: (id: string, status: ConnectionStatus, error?: string) => void;
  setConnected: (list: ConnectedDeviceSummary[]) => void;
  clearDevices: () => void;
  reset: () => void;
}

export const useDeviceStore = create<DeviceState>((set) => ({
  devices: {},
  connected: [],
  isScanning: false,
  error: null,

  setScanning: (isScanning) => set({ isScanning }),
  setError: (error) => set({ error }),

  upsertDevice: (partial) =>
    set((state) => {
      const existing = state.devices[partial.id];
      return {
        devices: {
          ...state.devices,
          [partial.id]: {
            id: partial.id,
            // Prefer the newly received name when present — BLE sometimes
            // advertises the name in a later packet than the initial
            // discovery, and we don't want to stick with "unnamed".
            name: partial.name ?? existing?.name ?? null,
            rssi: partial.rssi ?? existing?.rssi ?? null,
            address: partial.address || existing?.address || "",
            status: existing?.status ?? "disconnected",
            lastError: existing?.lastError,
          },
        },
      };
    }),

  updateStatus: (id, status, error) =>
    set((state) => {
      const existing = state.devices[id];
      if (!existing) {
        // A connection-state event for a device we never discovered — still
        // track it so the UI doesn't lose the status. Address/RSSI are
        // unknown; they'll be filled in if/when discovery sees it.
        return {
          devices: {
            ...state.devices,
            [id]: {
              id,
              name: null,
              rssi: null,
              address: "",
              status,
              lastError: error,
            },
          },
        };
      }
      return {
        devices: {
          ...state.devices,
          [id]: { ...existing, status, lastError: error },
        },
      };
    }),

  setConnected: (connected) => set({ connected }),

  clearDevices: () => set({ devices: {} }),

  reset: () =>
    set({ devices: {}, connected: [], isScanning: false, error: null }),
}));
