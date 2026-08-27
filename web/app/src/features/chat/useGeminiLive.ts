'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import type { TranscriptSegment } from '@/features/recording';
import type { ClientMessage } from '@/types/conversation';
import { createGeminiLiveSession, reportGeminiLiveUsage } from '@/features/chat/api';
import { GeminiLiveClient } from '@/lib/geminiLive';

export type GeminiLiveState = 'idle' | 'connecting' | 'listening' | 'paused';

export function createGeminiLiveStore() {
  const state = createSignal<GeminiLiveState>('idle');
  const level = createSignal(0);
  const duration = createSignal(0);
  const humanText = createSignal('');
  const aiText = createSignal('');
  const error = createSignal<string | null>(null);
  return { state, level, duration, humanText, aiText, error };
}

export function useGeminiLive({
  messages,
  onExchange,
}: {
  messages: ClientMessage[];
  onExchange: (humanText: string, aiText: string) => Promise<void>;
}) {
  const store = useMemo(() => createGeminiLiveStore(), []);
  const clientRef = useRef<GeminiLiveClient | null>(null);
  const messagesRef = useRef(messages);
  const exchangeRef = useRef(onExchange);
  messagesRef.current = messages;
  exchangeRef.current = onExchange;

  const state = useSignalValue(store.state);
  const level = useSignalValue(store.level);
  const duration = useSignalValue(store.duration);
  const humanText = useSignalValue(store.humanText);
  const aiText = useSignalValue(store.aiText);
  const error = useSignalValue(store.error);

  useEffect(() => {
    if (state !== 'listening') return;
    const interval = window.setInterval(() => store.duration.set((value) => value + 1), 1000);
    return () => window.clearInterval(interval);
  }, [state, store]);

  useEffect(() => () => clientRef.current?.stop(), []);

  const start = useCallback(async () => {
    if (clientRef.current) return;
    store.error.set(null);
    store.duration.set(0);
    store.level.set(0);
    store.state.set('connecting');
    const history = messagesRef.current
      .slice(-20)
      .map((message) => ({ sender: message.sender, text: message.text }))
      .filter((message) => message.text.trim())
      .reduceRight<{ sender: 'human' | 'ai'; text: string }[]>((current, message) => {
        const used = current.reduce((total, item) => total + item.text.length, 0);
        return used + message.text.length <= 6000 ? [message, ...current] : current;
      }, []);
    let client: GeminiLiveClient;
    client = new GeminiLiveClient(
      {
        onReady: () => {
          if (clientRef.current === client) store.state.set('listening');
        },
        onLevel: (nextLevel) => {
          if (clientRef.current === client) store.level.set(nextLevel);
        },
        onTranscript: (human, ai) => {
          if (clientRef.current !== client) return;
          store.humanText.set(human);
          store.aiText.set(ai);
        },
        onExchange: (human, ai) => {
          void exchangeRef
            .current(human, ai)
            .catch(() => store.error.set('Live conversation was not saved to chat history'));
        },
        onUsage: (report) => {
          void reportGeminiLiveUsage(report).catch(() =>
            store.error.set('Gemini Live usage could not be recorded'),
          );
        },
        onError: (message) => {
          if (clientRef.current === client) store.error.set(message);
        },
        onClose: () => {
          if (clientRef.current !== client) return;
          clientRef.current = null;
          store.state.set('idle');
          store.level.set(0);
        },
      },
      history,
    );
    clientRef.current = client;
    try {
      const session = await createGeminiLiveSession();
      if (clientRef.current !== client) return;
      client.connect(session.token);
    } catch (caught) {
      clientRef.current = null;
      store.state.set('idle');
      store.error.set(caught instanceof Error ? caught.message : 'Could not start Gemini Live');
    }
  }, [store]);

  const stop = useCallback(() => {
    clientRef.current?.stop();
    clientRef.current = null;
    store.state.set('idle');
    store.level.set(0);
    store.humanText.set('');
    store.aiText.set('');
  }, [store]);

  const pause = useCallback(() => {
    clientRef.current?.pause();
    store.state.set('paused');
    store.level.set(0);
  }, [store]);

  const resume = useCallback(() => {
    clientRef.current?.resume();
    store.state.set('listening');
  }, [store]);

  const segments = useMemo<TranscriptSegment[]>(() => {
    const current: TranscriptSegment[] = [];
    if (humanText) {
      current.push({
        id: 'gemini-human',
        text: humanText,
        speaker: 0,
        isUser: true,
        timestamp: 0,
      });
    }
    if (aiText) {
      current.push({
        id: 'gemini-ai',
        text: aiText,
        speaker: 1,
        isUser: false,
        timestamp: 0,
      });
    }
    return current;
  }, [aiText, humanText]);

  return {
    state,
    level,
    duration,
    segments,
    error,
    start,
    stop,
    pause,
    resume,
  };
}
