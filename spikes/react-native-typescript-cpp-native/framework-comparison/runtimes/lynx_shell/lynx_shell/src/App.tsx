import { useEffect, useState } from '@lynx-js/react';

import './App.css';
import {
  connectOmi,
  getBluetoothState,
  getNativeCapabilities,
  getOmiScanResults,
  normalizePacket,
  startOmiScan,
  stopOmiScan,
  type BluetoothState,
  type OmiDevice,
} from './native/omiNative';

export function App(props: { onRender?: () => void }) {
  const [nativeCapabilities, setNativeCapabilities] = useState('not connected');
  const [nativePacketStatus, setNativePacketStatus] = useState('not tested');
  const [bluetooth, setBluetooth] = useState<BluetoothState>({});
  const [devices, setDevices] = useState<OmiDevice[]>([]);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    setNativeCapabilities(getNativeCapabilities());
    setNativePacketStatus(normalizePacket(''));
    setBluetooth(getBluetoothState());
  }, []);
  props.onRender?.();

  const scan = () => {
    const state = startOmiScan();
    setBluetooth(state);
    if (!state.scanActive) return;
    setScanning(true);
    setTimeout(() => {
      const stopped = stopOmiScan();
      setDevices(getOmiScanResults());
      setBluetooth(stopped);
      setScanning(false);
    }, 4000);
  };

  const connect = (device: OmiDevice) => setBluetooth(connectOmi(device.id));

  return (
    <scroll-view scroll-orientation="vertical" className="Page">
      <view {...({ sticky: true, flatten: false } as Record<string, unknown>)} className="TopBar">
        <text className="Wordmark">omi</text>
        <text className="SmallLink">spike</text>
      </view>

      <view className="Hero">
        <text className="Greeting">Hi, I’m Omi</text>
        <text className="Subtitle">Connect the real Omi device nearby.</text>
        <view className="Connection">
          <view className="Dot" />
          <text>{bluetooth.connection === 'connected' ? 'Omi is connected' : 'Bluetooth is not connected'}</text>
        </view>

        <view className="ListenButton" bindtap={scan}>
          <text className="ListenIcon">⌁</text>
          <text className="ListenLabel">{scanning ? 'Looking for Omi…' : 'Find my Omi'}</text>
          <text className="ListenHint">Uses the phone’s real Bluetooth adapter</text>
        </view>
      </view>

      <view className="TodayCard">
        <text className="CardTitle">Nearby Omi devices</text>
        {devices.length === 0 ? (
          <view className="EmptyState">
            <text className="EmptyNumber">—</text>
            <text className="CardNote">Tap “Find my Omi” while your device is advertising.</text>
          </view>
        ) : devices.map((device) => (
          <view className="DeviceRow" bindtap={() => connect(device)} key={device.id}>
            <view className="DeviceCircle"><text>omi</text></view>
            <view className="DeviceWords">
              <text className="DeviceName">{device.name || 'Omi'}</text>
              <text className="DeviceDetail">{device.id} · RSSI {device.rssi} · Tap to connect</text>
            </view>
          </view>
        ))}
      </view>

      <view className="DeviceCard">
        <text className="CardTitle">Bluetooth adapter</text>
        <text className="CardNote">State: {bluetooth.state ?? 'unknown'}</text>
        <text className="CardNote">Implementation: {bluetooth.implementation ?? 'unavailable'}</text>
        {bluetooth.lastError ? <text className="CardNote">Error: {bluetooth.lastError}</text> : null}
      </view>

      <view className="NativeCard">
        <text className="CardTitle">Phone connection</text>
        <text className="CardNote">Lynx bridge: {nativeCapabilities}</text>
        <text className="CardNote">Packet check: {nativePacketStatus}</text>
      </view>

      <text className="Footer">This uses real Omi GATT discovery. Audio notifications and capture controls come after the connection path is verified on hardware.</text>
    </scroll-view>
  );
}
