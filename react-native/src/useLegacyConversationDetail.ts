import {useEffect, useRef, useState} from 'react';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from './omiNative';
import {
  legacyConversationDetailErrorCopy,
  loadLegacyConversationDetail,
  type LegacyConversationDetail,
} from './legacyConversationDetail';

export type LegacyConversationDetailRead =
  | {status: 'idle'; conversationId: null}
  | {status: 'loading'; conversationId: string}
  | {status: 'error'; conversationId: string; error: string}
  | {status: 'loaded'; conversationId: string; value: LegacyConversationDetail};

export function useLegacyConversationDetail(
  conversationId: string | null,
  revision?: string | null,
) {
  const [result, setResult] = useState<LegacyConversationDetailRead>({
    status: 'idle',
    conversationId: null,
  });
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  const request = useRef<AbortController | null>(null);
  useEffect(
    () =>
      subscribeOmiBackendSessionInvalidated(() => {
        epoch.current++;
        request.current?.abort();
        setResult(previous =>
          previous.conversationId === null
            ? previous
            : {
                status: 'error',
                conversationId: previous.conversationId,
                error: 'Sign in again to read this conversation.',
              },
        );
      }),
    [],
  );
  useEffect(() => {
    const lifetime = epoch;
    const current = ++lifetime.current;
    const controller = new AbortController();
    request.current = controller;
    if (conversationId === null) {
      setResult({status: 'idle', conversationId: null});
    } else {
      setResult({status: 'loading', conversationId});
      const load = async () => {
        try {
          if (omiBackend == null) {
            throw new Error('Native transport unavailable');
          }
          const value = await loadLegacyConversationDetail(
            omiBackend,
            conversationId,
            controller.signal,
          );
          if (!controller.signal.aborted && epoch.current === current) {
            setResult({status: 'loaded', conversationId, value});
          }
        } catch (error) {
          if (!controller.signal.aborted && epoch.current === current) {
            setResult({
              status: 'error',
              conversationId,
              error: legacyConversationDetailErrorCopy(error),
            });
          }
        }
      };
      load();
    }
    return () => {
      controller.abort();
      lifetime.current++;
    };
  }, [conversationId, revision, reload]);
  return {
    result:
      result.conversationId === conversationId
        ? result
        : ({status: 'idle', conversationId: null} as const),
    reload: () => setReload(value => value + 1),
  };
}
