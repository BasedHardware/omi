import { useEffect, useMemo } from "react";
import { Bluetooth, BluetoothOff, RefreshCw, Wifi } from "lucide-react";
import { PageHeader } from "../ui/page-header";
import { useDeviceStore } from "../../stores/deviceStore";
import {
  connect,
  disconnect,
  initBluetooth,
  listConnected,
  startScan,
  stopScan,
} from "../../services/bluetooth";

/**
 * Device Settings — Bluetooth discovery and pairing.
 *
 * Ports the discovery + pairing slice of `DeviceSettingsPage.swift` from the
 * macOS app. Audio streaming / firmware introspection are intentionally out
 * of scope here; this page only covers scan, pair, and list.
 *
 * Visual language follows `MemoriesPage.tsx`: `PageHeader` for the top bar,
 * a scrollable content region below, and a single column of cards for
 * device rows. Styling lives in `globals.css` under the "Devices" section.
 */
export function DeviceSettingsPage() {
  const devices = useDeviceStore((s) => s.devices);
  const connected = useDeviceStore((s) => s.connected);
  const isScanning = useDeviceStore((s) => s.isScanning);
  const error = useDeviceStore((s) => s.error);

  useEffect(() => {
    // Wire event listeners once per mount. `initBluetooth` is idempotent —
    // the returned unlisten aggregates both subscriptions so teardown is
    // atomic when the page is unmounted.
    let unlisten: (() => void) | null = null;
    void initBluetooth().then((u) => {
      unlisten = u;
    });
    // Pull the current connected list so the "Connected" section populates
    // even if the user has never opened this page before.
    void listConnected();
    return () => {
      if (unlisten) unlisten();
      // Proactively stop an in-flight scan when leaving the page — the OS
      // radio is a shared resource and leaving it scanning burns battery
      // on laptops / mobile devices.
      if (useDeviceStore.getState().isScanning) {
        void stopScan();
      }
    };
  }, []);

  // Discovered list (exclude already-connected — they render in their own
  // section). Sort by signal strength so the strongest nearby devices are
  // at the top, matching the Swift app's `sort { $0.rssi > $1.rssi }`.
  const discovered = useMemo(() => {
    const connectedIds = new Set(connected.map((d) => d.id));
    return Object.values(devices)
      .filter((d) => !connectedIds.has(d.id))
      .sort((a, b) => (b.rssi ?? -999) - (a.rssi ?? -999));
  }, [devices, connected]);

  const onToggleScan = () => {
    if (isScanning) void stopScan();
    else void startScan();
  };

  return (
    <div className="devices-page">
      <PageHeader
        title="Devices"
        subtitle={
          isScanning
            ? "Scanning for nearby Bluetooth devices…"
            : connected.length > 0
              ? `${connected.length} connected`
              : "No devices connected"
        }
        actions={
          <button
            type="button"
            className="devices-scan-btn"
            onClick={onToggleScan}
            aria-label={isScanning ? "Stop scanning" : "Start scanning"}
          >
            {isScanning ? (
              <>
                <RefreshCw className="devices-scan-icon devices-scan-icon-spin" />
                <span>Stop</span>
              </>
            ) : (
              <>
                <Bluetooth className="devices-scan-icon" />
                <span>Scan</span>
              </>
            )}
          </button>
        }
      />

      <div className="devices-content">
        {error && (
          <div className="devices-error" role="alert">
            <BluetoothOff className="devices-error-icon" />
            <div>
              <div className="devices-error-title">
                Bluetooth unavailable
              </div>
              <div className="devices-error-body">{error}</div>
            </div>
          </div>
        )}

        {/* Connected devices */}
        {connected.length > 0 && (
          <section className="devices-section">
            <h2 className="devices-section-title">Connected</h2>
            <div className="devices-list">
              {connected.map((device) => (
                <ConnectedRow
                  key={device.id}
                  id={device.id}
                  name={device.name}
                  address={device.address}
                />
              ))}
            </div>
          </section>
        )}

        {/* Discovery results */}
        <section className="devices-section">
          <h2 className="devices-section-title">
            {isScanning ? "Nearby" : "Discovered"}
          </h2>
          {discovered.length === 0 ? (
            <EmptyState isScanning={isScanning} hasError={!!error} />
          ) : (
            <div className="devices-list">
              {discovered.map((device) => (
                <DiscoveredRow key={device.id} device={device} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ConnectedRow({
  id,
  name,
  address,
}: {
  id: string;
  name: string | null;
  address: string;
}) {
  return (
    <div className="device-row device-row-connected">
      <div className="device-row-icon">
        <Bluetooth className="device-row-icon-svg" />
      </div>
      <div className="device-row-info">
        <div className="device-row-name">{name || "Unnamed device"}</div>
        <div className="device-row-meta">
          <span className="device-row-dot device-row-dot-connected" />
          Connected
          {address && <span className="device-row-address">{address}</span>}
        </div>
      </div>
      <button
        type="button"
        className="device-row-action device-row-action-destructive"
        onClick={() => void disconnect(id)}
      >
        Disconnect
      </button>
    </div>
  );
}

function DiscoveredRow({
  device,
}: {
  device: ReturnType<typeof useDeviceStore.getState>["devices"][string];
}) {
  const status = device.status;
  const isBusy = status === "connecting";
  const hasFailed = status === "failed";

  return (
    <div className="device-row">
      <div className="device-row-icon">
        <Bluetooth className="device-row-icon-svg" />
      </div>
      <div className="device-row-info">
        <div className="device-row-name">{device.name || "Unnamed device"}</div>
        <div className="device-row-meta">
          {device.rssi !== null && (
            <span className="device-row-rssi">
              <Wifi className="device-row-rssi-icon" />
              {device.rssi} dBm
            </span>
          )}
          {device.address && (
            <span className="device-row-address">{device.address}</span>
          )}
          {hasFailed && device.lastError && (
            <span className="device-row-error">{device.lastError}</span>
          )}
        </div>
      </div>
      <button
        type="button"
        className="device-row-action"
        onClick={() => void connect(device.id)}
        disabled={isBusy}
      >
        {isBusy ? "Connecting…" : hasFailed ? "Retry" : "Connect"}
      </button>
    </div>
  );
}

function EmptyState({
  isScanning,
  hasError,
}: {
  isScanning: boolean;
  hasError: boolean;
}) {
  if (hasError) {
    return (
      <div className="devices-empty">
        Check that Bluetooth is enabled and that the app has permission to
        use it.
      </div>
    );
  }
  if (isScanning) {
    return <div className="devices-empty">Looking for nearby devices…</div>;
  }
  return (
    <div className="devices-empty">
      No devices yet. Tap Scan to look for nearby Bluetooth devices.
    </div>
  );
}
