import {useEffect, useRef, useState} from 'react';
import {
  ChatBackendError,
  chatHistoryCanReload,
  chatHistoryErrorCopy,
  loadNewestChatHistory,
  loadOlderChatHistory,
  mergeOlderChatHistory,
  type ChatMessage,
} from './chatClient';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from './omiNative';

export const MAIN_CHAT_CONVERSATION_ID = 'chat:chat-main';

type ChatHistoryRead =
  | {status: 'idle'}
  | {status: 'loading'}
  | {status: 'error'; error: string; canReload: boolean}
  | {
      status: 'loaded';
      messages: ChatMessage[];
      olderCursor: string | null;
      hasOlder: boolean;
    };

export function useChatConversationHistory(active: boolean) {
  const [result, setResult] = useState<ChatHistoryRead>({status: 'idle'});
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  useEffect(
    () =>
      subscribeOmiBackendSessionInvalidated(() => {
        epoch.current++;
        setLoadingOlder(false);
        setResult(previous =>
          previous.status === 'idle'
            ? previous
            : {
                status: 'error',
                error: chatHistoryErrorCopy({
                  code: 'OMI_HTTP_UNAUTHORIZED',
                }),
                canReload: true,
              },
        );
      }),
    [],
  );
  useEffect(() => {
    const current = ++epoch.current;
    let alive = true;
    if (!active) {
      setLoadingOlder(false);
      setResult({status: 'idle'});
      return () => {
        alive = false;
      };
    }
    setLoadingOlder(false);
    setResult({status: 'loading'});
    const load = async () => {
      try {
        if (omiBackend == null) {
          throw new Error('Native transport unavailable');
        }
        const page = await loadNewestChatHistory(omiBackend);
        if (!alive || epoch.current !== current) {
          return;
        }
        setResult({
          status: 'loaded',
          messages: page.messages,
          olderCursor: page.olderCursor,
          hasOlder: page.hasOlder,
        });
      } catch (error) {
        if (alive && epoch.current === current) {
          setResult({
            status: 'error',
            error: chatHistoryErrorCopy(error),
            canReload: chatHistoryCanReload(error),
          });
        }
      }
    };
    void load();
    return () => {
      alive = false;
    };
  }, [active, reload]);
  return {
    result,
    loadingOlder,
    loadOlder: async () => {
      if (
        result.status !== 'loaded' ||
        !result.hasOlder ||
        result.olderCursor === null ||
        loadingOlder
      ) {
        return;
      }
      const current = epoch.current;
      const cursor = result.olderCursor;
      setLoadingOlder(true);
      try {
        if (omiBackend == null) {
          throw new Error('Native transport unavailable');
        }
        const page = await loadOlderChatHistory(omiBackend, cursor);
        if (epoch.current !== current) {
          return;
        }
        setResult(previous =>
          previous.status === 'loaded'
            ? {
                status: 'loaded',
                messages: mergeOlderChatHistory(
                  previous.messages,
                  page.messages,
                ),
                olderCursor: page.olderCursor,
                hasOlder: page.hasOlder,
              }
            : previous,
        );
      } catch (error) {
        if (epoch.current !== current) {
          return;
        }
        if (
          error instanceof ChatBackendError &&
          error.status === 410 &&
          error.action === 'refresh_history'
        ) {
          setReload(value => value + 1);
          return;
        }
        setResult({
          status: 'error',
          error: chatHistoryErrorCopy(error),
          canReload: chatHistoryCanReload(error),
        });
      } finally {
        if (epoch.current === current) {
          setLoadingOlder(false);
        }
      }
    },
    reload: () => setReload(value => value + 1),
  };
}
