import React, {useCallback, useEffect, useRef, useState} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import Mic from 'lucide-react-native/icons/mic';
import PhoneOff from 'lucide-react-native/icons/phone-off';
import type {OmiBackend} from '../omiNativeTypes';
import type {LiveVoiceProvider} from '../desktopSettingsClient';
import {
  LiveUnsupportedError,
  liveErrorCopy,
  liveGeminiSupported,
  requestLiveSession,
} from '../liveClient';
import {
  LiveWebRtcSession,
  resolveLiveWebRtcScope,
  type LiveVoicePhase,
} from '../liveWebRtc';
import {LiveGeminiSession, resolveLiveGeminiScope} from '../liveGemini';
import {FocusPressable} from './Pressable';
import {desktopTokens} from '../desktop/tokens';
import {mobileColor} from '../mobile/mobileTokens';

type Props = {
  backend: OmiBackend | null | undefined;
  compact?: boolean;
  desktop?: boolean;
  provider?: LiveVoiceProvider;
};

type ActiveSession = {
  stop(): void;
};

export function LiveVoiceButton({
  backend,
  compact = false,
  desktop = false,
  provider = 'gpt_live',
}: Props) {
  const [phase, setPhase] = useState<LiveVoicePhase>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const sessionRef = useRef<ActiveSession | null>(null);
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

  // Switching providers mid-call ends the active session honestly.
  useEffect(() => {
    if (sessionRef.current !== null) {
      sessionRef.current.stop();
      sessionRef.current = null;
      setPhase('idle');
      setMessage(null);
    }
  }, [provider]);

  const start = useCallback(async () => {
    if (backend === null || backend === undefined) {
      setMessage('Sign in again to use Live voice.');
      setPhase('error');
      return;
    }
    setMessage(null);
    setPhase('connecting');

    const onPhase = (next: LiveVoicePhase, detail?: string) => {
      setPhase(next);
      setMessage(next === 'error' ? detail ?? null : null);
      if (next === 'closed' || next === 'error') {
        sessionRef.current = null;
      }
    };

    if (provider === 'gemini_live') {
      const scope = resolveLiveGeminiScope();
      if (scope === null || !liveGeminiSupported()) {
        setMessage(
          liveErrorCopy(
            new LiveUnsupportedError(
              'Gemini Live needs microphone streaming on this device.',
            ),
            provider,
          ),
        );
        setPhase('error');
        return;
      }
      const session = new LiveGeminiSession(
        scope,
        async () => {
          const minted = await requestLiveSession(backend, {
            provider: 'gemini_live',
          });
          if (minted.provider !== 'gemini_live') {
            throw new Error(
              'Live session response used an unsupported transport',
            );
          }
          return minted;
        },
        {onPhase},
      );
      sessionRef.current = session;
      await session.start();
      return;
    }

    const scope = resolveLiveWebRtcScope();
    if (scope === null) {
      setMessage(liveErrorCopy(new LiveUnsupportedError(), provider));
      setPhase('error');
      return;
    }
    const session = new LiveWebRtcSession(
      scope,
      async sdp => {
        const minted = await requestLiveSession(backend, {
          provider: 'gpt_live',
          sdp,
        });
        if (minted.provider !== 'gpt_live') {
          throw new Error(
            'Live session response used an unsupported transport',
          );
        }
        return minted;
      },
      {onPhase},
    );
    sessionRef.current = session;
    await session.start();
  }, [backend, provider]);

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
