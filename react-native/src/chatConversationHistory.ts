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

export function chatHistorySessionId(
  conversationId: string,
): string | undefined {
  if (
    conversationId === MAIN_CHAT_CONVERSATION_ID ||
    !conversationId.startsWith('chat:')
  ) {
    return undefined;
  }
  const sessionId = conversationId.slice('chat:'.length);
  return sessionId.length === 0 ? undefined : sessionId;
}

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

export function useChatConversationHistory(
  active: boolean,
  conversationId: string,
) {
  const [result, setResult] = useState<ChatHistoryRead>({status: 'idle'});
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderNotice, setOlderNotice] = useState<string | null>(null);
  const [olderRetryable, setOlderRetryable] = useState(true);
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  useEffect(
    () =>
      subscribeOmiBackendSessionInvalidated(() => {
        epoch.current++;
        setLoadingOlder(false);
        setOlderNotice(null);
        setOlderRetryable(true);
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
      setOlderNotice(null);
      setOlderRetryable(true);
      setResult({status: 'idle'});
      return () => {
        alive = false;
      };
    }
    setLoadingOlder(false);
    setOlderNotice(null);
    setOlderRetryable(true);
    setResult({status: 'loading'});
    const load = async () => {
      try {
        if (omiBackend == null) {
          throw new Error('Native transport unavailable');
        }
        const page = await loadNewestChatHistory(
          omiBackend,
          chatHistorySessionId(conversationId),
        );
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
  }, [active, reload, conversationId]);
  return {
    result,
    loadingOlder,
    olderNotice,
    olderRetryable,
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
      setOlderNotice(null);
      setOlderRetryable(true);
      try {
        if (omiBackend == null) {
          throw new Error('Native transport unavailable');
        }
        const page = await loadOlderChatHistory(
          omiBackend,
          cursor,
          chatHistorySessionId(conversationId),
        );
        if (epoch.current !== current) {
          return;
        }
        setOlderNotice(null);
        setOlderRetryable(true);
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
        setOlderNotice(chatHistoryErrorCopy(error));
        setOlderRetryable(chatHistoryCanReload(error));
      } finally {
        if (epoch.current === current) {
          setLoadingOlder(false);
        }
      }
    },
    reload: () => setReload(value => value + 1),
  };
}
