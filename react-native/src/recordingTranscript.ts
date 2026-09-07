import {useEffect, useRef, useState} from 'react';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from './omiNative';

import {
  parseRecordingTranscript,
  type RecordingTranscript,
} from './recordingTranscriptContract';

type TranscriptRead =
  | {status: 'idle'; sessionId: null}
  | {status: 'loading'; sessionId: string}
  | {status: 'error'; sessionId: string; retryable: boolean}
  | {status: 'loaded'; sessionId: string; value: RecordingTranscript};

function transcriptErrorRetryable(status: number, body: string | null): boolean {
  if (body !== null) {
    try {
      const parsed = JSON.parse(body) as {
        error?: {retryable?: unknown} | string;
      };
      if (
        parsed.error !== null &&
        typeof parsed.error === 'object' &&
        typeof parsed.error.retryable === 'boolean'
      ) {
        return parsed.error.retryable;
      }
    } catch {}
  }
  return [408, 429, 500, 502, 503, 504].includes(status);
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
            : {status: 'error', sessionId: previous.sessionId, retryable: true},
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
            ? {
                status: 'error',
                sessionId,
                retryable: transcriptErrorRetryable(
                  response.status,
                  response.body,
                ),
              }
            : {status: 'loaded', sessionId, value},
        );
      } catch {
        if (active && epoch.current === current) {
          setResult({status: 'error', sessionId, retryable: true});
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
        (result.value.state === 'queued' || result.value.state === 'running')
          ? sessionId
          : null;
      setReload(value => value + 1);
    },
  };
}
