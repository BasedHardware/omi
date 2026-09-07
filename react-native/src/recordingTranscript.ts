import {useEffect, useRef, useState} from 'react';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from './omiNative';

export type RecordingTranscript = {
  sessionId: string;
  state: 'queued' | 'running' | 'completed' | 'failed';
  text: string | null;
  discardedLeadingPackets: number;
};

type TranscriptRead =
  | {status: 'idle'; sessionId: null}
  | {status: 'loading'; sessionId: string}
  | {status: 'error'; sessionId: string}
  | {status: 'loaded'; sessionId: string; value: RecordingTranscript};

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function parseRecordingTranscript(
  body: string | null,
  sessionId: string,
): RecordingTranscript | null {
  if (body === null || body.length > 3_000_000) {
    return null;
  }
  try {
    const envelope: unknown = JSON.parse(body);
    if (!record(envelope) || !record(envelope.transcription)) {
      return null;
    }
    const value = envelope.transcription;
    if (
      value.sessionId !== sessionId ||
      !['queued', 'running', 'completed', 'failed'].includes(
        value.state as string,
      ) ||
      !(value.text === null || typeof value.text === 'string') ||
      (value.state === 'completed' && typeof value.text !== 'string') ||
      !Array.isArray(value.segments) ||
      !(value.language === null || typeof value.language === 'string') ||
      !(value.errorCode === null || typeof value.errorCode === 'string') ||
      !Number.isSafeInteger(value.updatedAt) ||
      (value.updatedAt as number) < 0 ||
      !Number.isSafeInteger(value.discardedLeadingPackets) ||
      (value.discardedLeadingPackets as number) < 0
    ) {
      return null;
    }
    return {
      sessionId,
      state: value.state as RecordingTranscript['state'],
      text: value.text as string | null,
      discardedLeadingPackets: value.discardedLeadingPackets as number,
    };
  } catch {
    return null;
  }
}

export function useRecordingTranscript(
  sessionId: string | null,
  revision: string | undefined,
) {
  const [result, setResult] = useState<TranscriptRead>({
    status: 'idle',
    sessionId: null,
  });
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  const resume = useRef<string | null>(null);
  useEffect(
    () =>
      subscribeOmiBackendSessionInvalidated(() => {
        epoch.current++;
        setResult(previous =>
          previous.sessionId === null
            ? previous
            : {status: 'error', sessionId: previous.sessionId},
        );
      }),
    [],
  );
  useEffect(() => {
    const current = ++epoch.current;
    const resuming = sessionId !== null && resume.current === sessionId;
    resume.current = null;
    let active = true;
    if (sessionId === null) {
      setResult({status: 'idle', sessionId: null});
      return () => {
        active = false;
      };
    }
    setResult({status: 'loading', sessionId});
    const load = async () => {
      try {
        if (omiBackend == null) {
          throw new Error('Native transport unavailable');
        }
        const response = await omiBackend.request({
          id: `recording-transcript:${sessionId}:${current}`,
          method: resuming ? 'POST' : 'GET',
          path: `/v1/device-sessions/${encodeURIComponent(sessionId)}/${
            resuming ? 'transcribe' : 'transcript'
          }`,
        });
        const value =
          response.status === 200 || (resuming && response.status === 202)
            ? parseRecordingTranscript(response.body, sessionId)
            : null;
        if (!active || epoch.current !== current) {
          return;
        }
        setResult(
          value === null
            ? {status: 'error', sessionId}
            : {status: 'loaded', sessionId, value},
        );
      } catch {
        if (active && epoch.current === current) {
          setResult({status: 'error', sessionId});
        }
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [sessionId, revision, reload]);
  return {
    result:
      result.sessionId === sessionId
        ? result
        : ({status: 'idle', sessionId: null} as const),
    reload: () => {
      resume.current =
        result.sessionId === sessionId &&
        result.status === 'loaded' &&
        result.value.state !== 'completed'
          ? sessionId
          : null;
      setReload(value => value + 1);
    },
  };
}
