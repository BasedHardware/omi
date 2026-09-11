import React, {useCallback, useEffect, useRef, useState} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import Mic from 'lucide-react-native/icons/mic';
import PhoneOff from 'lucide-react-native/icons/phone-off';
import type {OmiBackend} from '../omiNativeTypes';
import {
  LiveUnsupportedError,
  liveErrorCopy,
  requestLiveSession,
} from '../liveClient';
import {
  LiveWebRtcSession,
  resolveLiveWebRtcScope,
  type LiveVoicePhase,
} from '../liveWebRtc';
import {FocusPressable} from './Pressable';
import {desktopTokens} from '../desktop/tokens';
import {mobileColor} from '../mobile/mobileTokens';

type Props = {
  backend: OmiBackend | null | undefined;
  compact?: boolean;
  desktop?: boolean;
};

export function LiveVoiceButton({
  backend,
  compact = false,
  desktop = false,
}: Props) {
  const [phase, setPhase] = useState<LiveVoicePhase>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const sessionRef = useRef<LiveWebRtcSession | null>(null);
  const active =
    phase === 'connecting' || phase === 'live' || phase === 'stopping';

  const stop = useCallback(() => {
    sessionRef.current?.stop();
    sessionRef.current = null;
  }, []);

  useEffect(() => {
    // A screen change or sign-out must not leave the microphone open.
    return () => {
      sessionRef.current?.stop();
      sessionRef.current = null;
    };
  }, []);

  const start = useCallback(async () => {
    if (backend === null || backend === undefined) {
      setMessage('Sign in again to use Live voice.');
      setPhase('error');
      return;
    }
    const scope = resolveLiveWebRtcScope();
    if (scope === null) {
      setMessage(liveErrorCopy(new LiveUnsupportedError()));
      setPhase('error');
      return;
    }
    setMessage(null);
    setPhase('connecting');
    const session = new LiveWebRtcSession(
      scope,
      sdp => requestLiveSession(backend, sdp),
      {
        onPhase: (next, detail) => {
          setPhase(next);
          setMessage(next === 'error' ? detail ?? null : null);
        },
      },
    );
    sessionRef.current = session;
    await session.start();
  }, [backend]);

  const toggle = useCallback(() => {
    if (active) {
      stop();
      return;
    }
    void start();
  }, [active, start, stop]);

  const ink = desktop
    ? desktopTokens.color.ink
    : compact
    ? mobileColor.text
    : desktopTokens.color.ink;
  const on = phase === 'live';
  const label = active ? 'End Live' : 'Live';
  return (
    <View style={styles.root}>
      <FocusPressable
        accessibilityLabel={active ? 'End Live voice' : 'Start Live voice'}
        accessibilityRole="button"
        accessibilityState={{busy: phase === 'connecting'}}
        onPress={toggle}
        style={({pressed}) => [
          styles.button,
          compact && styles.buttonCompact,
          on && styles.buttonOn,
          pressed && styles.pressed,
        ]}>
        {active ? (
          <PhoneOff color={on ? '#ffffff' : ink} size={16} />
        ) : (
          <Mic color={ink} size={16} />
        )}
        <Text style={[styles.label, on ? styles.labelOn : {color: ink}]}>
          {label}
        </Text>
      </FocusPressable>
      {message !== null ? (
        <Text accessibilityRole="alert" style={styles.message}>
          {message}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {alignItems: 'flex-start', gap: 4},
  button: {
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.06)',
    borderRadius: 14,
    flexDirection: 'row',
    gap: 6,
    minHeight: 32,
    paddingHorizontal: 12,
  },
  buttonCompact: {
    backgroundColor: mobileColor.surface,
    borderRadius: 18,
    minHeight: 40,
    paddingHorizontal: 14,
  },
  buttonOn: {backgroundColor: '#e5484d'},
  pressed: {opacity: 0.6},
  label: {fontSize: 13, fontWeight: '600'},
  labelOn: {color: '#ffffff'},
  message: {
    color: '#8a8a8e',
    fontSize: 12,
    maxWidth: 240,
  },
});
