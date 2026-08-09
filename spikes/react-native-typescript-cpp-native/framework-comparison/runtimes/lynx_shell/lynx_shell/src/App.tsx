import { useCallback, useEffect, useState } from '@lynx-js/react';

import './App.css';
import arrow from './assets/arrow.png';
import lynxLogo from './assets/lynx-logo.png';
import reactLynxLogo from './assets/react-logo.png';

const relayContract = 'omi-relay-contract:v1|native-seam:lynx-module|payload:bounded|gap:explicit';

type OmiNativeModule = {
  getNativeCapabilities?: () => string;
};

function readNativeCapabilities(): string {
  if (typeof NativeModules === 'undefined') return 'NATIVE_ADAPTER_UNAVAILABLE';
  const module = (NativeModules as { OmiNativeModule?: OmiNativeModule }).OmiNativeModule;
  return module?.getNativeCapabilities?.() ?? 'NATIVE_ADAPTER_UNAVAILABLE';
}

export function App(props: { onRender?: () => void }) {
  const [alterLogo, setAlterLogo] = useState(false);
  const [nativeCapabilities, setNativeCapabilities] = useState('NATIVE_ADAPTER_UNAVAILABLE');

  useEffect(() => {
    console.info('Hello, ReactLynx');
    setNativeCapabilities(readNativeCapabilities());
  }, []);
  props.onRender?.();

  const onTap = useCallback(() => {
    'background only';
    setAlterLogo((prevAlterLogo) => !prevAlterLogo);
  }, []);

  return (
    <view>
      <view className="Background" />
      <view className="App">
        <view className="Banner">
          <view className="Logo" bindtap={onTap}>
            {alterLogo ? (
              <image src={reactLynxLogo} className="Logo--react" />
            ) : (
              <image src={lynxLogo} className="Logo--lynx" />
            )}
          </view>
          <text className="Title">React</text>
          <text className="Subtitle">on Lynx</text>
        </view>
        <view className="Content">
          <image src={arrow} className="Arrow" />
          <text className="Description">Tap the logo and have fun!</text>
          <text className="Hint">{relayContract}</text>
          <text className="Hint">native:{nativeCapabilities}</text>
        </view>
        <view style={{ flex: 1 }} />
      </view>
    </view>
  );
}
