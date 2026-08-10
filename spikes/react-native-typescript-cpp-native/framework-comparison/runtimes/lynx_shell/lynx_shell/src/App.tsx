import { useEffect, useState } from '@lynx-js/react';

import './App.css';
import { getNativeCapabilities, normalizePacket } from './native/omiNative';

export function App(props: { onRender?: () => void }) {
  const [nativeCapabilities, setNativeCapabilities] = useState('not connected');
  const [nativePacketStatus, setNativePacketStatus] = useState('not tested');

  useEffect(() => {
    setNativeCapabilities(getNativeCapabilities());
    setNativePacketStatus(normalizePacket(''));
  }, []);
  props.onRender?.();

  return (
    <scroll-view scroll-orientation="vertical" className="Page">
      <view {...({ sticky: true, flatten: false } as Record<string, unknown>)} className="TopBar">
        <text className="Wordmark">omi</text>
        <text className="SmallLink">spike</text>
      </view>

      <view className="Hero">
        <text className="Greeting">Hi, I’m Omi</text>
        <text className="Subtitle">I help remember the things you say.</text>
        <view className="Connection">
          <view className="Dot" />
          <text>Bluetooth is not connected</text>
        </view>

        <view className="ListenButton ListenButton--disabled">
          <text className="ListenIcon">○</text>
          <text className="ListenLabel">Connect Omi</text>
          <text className="ListenHint">Bluetooth support is not wired yet</text>
        </view>
      </view>

      <view className="TodayCard">
        <text className="CardTitle">Today</text>
        <view className="EmptyState">
          <text className="EmptyNumber">—</text>
          <text className="CardNote">Moments will appear here after a real Omi is connected.</text>
        </view>
      </view>

      <view className="DeviceCard">
        <text className="CardTitle">Your Omi</text>
        <view className="DeviceRow">
          <view className="DeviceCircle"><text>omi</text></view>
          <view className="DeviceWords">
            <text className="DeviceName">No device connected</text>
            <text className="DeviceDetail">We will show your Omi here when Bluetooth is ready.</text>
          </view>
        </view>
      </view>

      <view className="NativeCard">
        <text className="CardTitle">Phone connection</text>
        <text className="CardNote">Lynx bridge: {nativeCapabilities}</text>
        <text className="CardNote">Packet check: {nativePacketStatus}</text>
      </view>

      <text className="Footer">This spike does not pretend to have BLE. Hardware support comes after the native adapter is implemented.</text>
    </scroll-view>
  );
}
