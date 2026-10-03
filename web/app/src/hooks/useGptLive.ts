'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TranscriptSegment } from '@/components/recording/RecordingContext';
import type { ClientMessage } from '@/types/conversation';
import { createGptLiveSession, reportGptLiveUsage } from '@/lib/api';
import {
  createGptLiveClient,
  DEFAULT_GPT_LIVE_INSTRUCTIONS,
  type GptLiveClient,
} from '@/lib/gptLive';

export type GptLiveState = 'idle' | 'connecting' | 'listening' | 'paused';

interface GptLiveHistoryMessage {
  sender: 'human' | 'ai';
  text: string;
}

function formatHistoryMessage(message: GptLiveHistoryMessage): string {
  const speaker = message.sender === 'human' ? 'User' : 'Assistant';
  return `${speaker}: ${message.text}`;
}

/**
 * Fold the recent transcript into the single `instructions` string the
 * GPT-Live session accepts, so a live turn continues from chat history.
 */
function buildInstructions(history: GptLiveHistoryMessage[]): string {
  if (history.length === 0) return DEFAULT_GPT_LIVE_INSTRUCTIONS;
  const transcript = history.map(formatHistoryMessage).join('\n');
  return `${DEFAULT_GPT_LIVE_INSTRUCTIONS}\n\nConversation so far:\n${transcript}`;
}

export function useGptLive({
  messages,
  onExchange,
}: {
  messages: ClientMessage[];
  onExchange: (humanText: string, aiText: string) => Promise<void>;
}) {
  const [state, setState] = useState<GptLiveState>('idle');
  const [level, setLevel] = useState(0);
  const [duration, setDuration] = useState(0);
  const [humanText, setHumanText] = useState('');
  const [aiText, setAiText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef<GptLiveClient | null>(null);
  const messagesRef = useRef(messages);
  const exchangeRef = useRef(onExchange);
  messagesRef.current = messages;
  exchangeRef.current = onExchange;

  useEffect(() => {
    if (state !== 'listening') return;
    const interval = window.setInterval(() => setDuration((value) => value + 1), 1000);
    return () => window.clearInterval(interval);
  }, [state]);

  useEffect(() => () => clientRef.current?.stop(), []);

  const start = useCallback(async () => {
    if (clientRef.current) return;
    setError(null);
    setDuration(0);
    setLevel(0);
    setState('connecting');
    const history = messagesRef.current
      .slice(-20)
      .map((message) => ({ sender: message.sender, text: message.text }))
      .filter((message) => message.text.trim())
      .reduceRight<GptLiveHistoryMessage[]>((current, message) => {
        const used = current.reduce((total, item) => total + item.text.length, 0);
        return used + message.text.length <= 6000 ? [message, ...current] : current;
      }, []);
    let client: GptLiveClient;
    client = createGptLiveClient({
      instructions: buildInstructions(history),
      onReady: () => {
        if (clientRef.current === client) setState('listening');
      },
      onLevel: (nextLevel) => {
        if (clientRef.current === client) setLevel(nextLevel);
      },
      onInputTranscript: (human) => {
        if (clientRef.current === client) setHumanText(human);
      },
      onOutputTranscript: (ai) => {
        if (clientRef.current === client) setAiText(ai);
      },
      onExchange: (human, ai) => {
        void exchangeRef
          .current(human, ai)
          .catch(() => setError('Live conversation was not saved to chat history'));
      },
      onUsage: (report) => {
        void reportGptLiveUsage(report).catch(() =>
          setError('GPT Live usage could not be recorded'),
        );
      },
      onInterrupted: () => {
        if (clientRef.current === client) setAiText('');
      },
      onError: (message) => {
        if (clientRef.current === client) setError(message);
      },
      onClose: () => {
        if (clientRef.current !== client) return;
        clientRef.current = null;
        setState('idle');
        setLevel(0);
      },
    });
    clientRef.current = client;
    try {
      const session = await createGptLiveSession();
      if (clientRef.current !== client) return;
      client.connect(session.token);
    } catch (caught) {
      clientRef.current = null;
      setState('idle');
      setError(caught instanceof Error ? caught.message : 'Could not start GPT Live');
    }
  }, []);

  const stop = useCallback(() => {
    clientRef.current?.stop();
    clientRef.current = null;
    setState('idle');
    setLevel(0);
    setHumanText('');
    setAiText('');
  }, []);

  const pause = useCallback(() => {
    clientRef.current?.pause();
    setState('paused');
    setLevel(0);
  }, []);

  const resume = useCallback(() => {
    clientRef.current?.resume();
    setState('listening');
  }, []);

  const segments = useMemo<TranscriptSegment[]>(() => {
    const current: TranscriptSegment[] = [];
    if (humanText) {
      current.push({
        id: 'gpt-live-human',
        text: humanText,
        speaker: 0,
        isUser: true,
        timestamp: 0,
      });
    }
    if (aiText) {
      current.push({
        id: 'gpt-live-ai',
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
