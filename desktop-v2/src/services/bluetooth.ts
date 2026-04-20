import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import {
  useDeviceStore,
  type ConnectionStatus,
  type ConnectedDeviceSummary,
} from "../stores/deviceStore";

/**
 * Thin wrapper over the Rust `bluetooth_*` commands.
 *
 * Responsibilities:
 * - Expose a typed, promise-based API for the UI (`startScan`, `stopScan`,
 *   `connect`, `disconnect`, `listConnected`).
 * - Own the lifecycle of the Tauri event listeners that push device updates
 *   into `deviceStore` — callers call `initBluetooth()` once and get back
 *   an unsubscribe for clean teardown.
 *
 * Event contract (must match `src-tauri/src/commands/bluetooth.rs`):
 *   bluetooth://device-found       { id, name, rssi, address }
 *   bluetooth://connection-state   { id, status, error? }
 */

interface DeviceFoundPayload {
  id: string;
  name: string | null;
  rssi: number | null;
  address: string;
}

interface ConnectionStatePayload {
  id: string;
  status: ConnectionStatus;
  error?: string;
}

let initPromise: Promise<UnlistenFn> | null = null;

/**
 * Subscribe the store to Rust-side Bluetooth events. Safe to call from
 * multiple components — subsequent calls reuse the first subscription.
 */
export async function initBluetooth(): Promise<UnlistenFn> {
  if (initPromise) return initPromise;

  initPromise = (async () => {
    const unlistenDevice = await listen<DeviceFoundPayload>(
      "bluetooth://device-found",
      (event) => {
        useDeviceStore.getState().upsertDevice(event.payload);
      },
    );

    const unlistenState = await listen<ConnectionStatePayload>(
      "bluetooth://connection-state",
      (event) => {
        const { id, status, error } = event.payload;
        useDeviceStore.getState().updateStatus(id, status, error);
        // After a successful connect/disconnect the connected-device list
        // is worth re-fetching — it feeds the "Connected" section of the
        // settings page. Fire-and-forget; errors are already reflected in
        // the per-device status.
        if (status === "connected" || status === "disconnected") {
          void listConnected();
        }
      },
    );

    return () => {
      unlistenDevice();
      unlistenState();
    };
  })();

  return initPromise;
}

export async function startScan(): Promise<void> {
  const store = useDeviceStore.getState();
  store.setError(null);
  // Clear stale results from a previous scan so the UI doesn't conflate
  // devices from different rooms / sessions. Connected devices are
  // preserved via the separate `connected` list.
  store.clearDevices();
  try {
    await invoke("bluetooth_start_scan");
    store.setScanning(true);
  } catch (e) {
    const msg = errorMessage(e);
    store.setError(msg);
    store.setScanning(false);
    throw e;
  }
}

export async function stopScan(): Promise<void> {
  try {
    await invoke("bluetooth_stop_scan");
  } finally {
    useDeviceStore.getState().setScanning(false);
  }
}

export async function connect(id: string): Promise<void> {
  useDeviceStore.getState().updateStatus(id, "connecting");
  try {
    await invoke("bluetooth_connect", { id });
  } catch (e) {
    const msg = errorMessage(e);
    useDeviceStore.getState().updateStatus(id, "failed", msg);
    throw e;
  }
}

export async function disconnect(id: string): Promise<void> {
  try {
    await invoke("bluetooth_disconnect", { id });
  } catch (e) {
    const msg = errorMessage(e);
    useDeviceStore.getState().updateStatus(id, "failed", msg);
    throw e;
  }
}

export async function listConnected(): Promise<ConnectedDeviceSummary[]> {
  try {
    const list = await invoke<ConnectedDeviceSummary[]>(
      "bluetooth_list_connected",
    );
    useDeviceStore.getState().setConnected(list);
    return list;
  } catch (e) {
    useDeviceStore.getState().setError(errorMessage(e));
    return [];
  }
}

function errorMessage(e: unknown): string {
  if (typeof e === "string") return e;
  if (e instanceof Error) return e.message;
  try {
    return JSON.stringify(e);
  } catch {
    return String(e);
  }
}
