import {useEffect, useRef, useState} from 'react';
import {
  chatHistoryErrorCopy,
  loadChatHistory,
  type ChatMessage,
} from './chatClient';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from './omiNative';

export const MAIN_CHAT_CONVERSATION_ID = 'chat:chat-main';

type ChatHistoryRead =
  | {status: 'idle'}
  | {status: 'loading'}
  | {status: 'error'; error: string}
  | {status: 'loaded'; messages: ChatMessage[]};

export function useChatConversationHistory(active: boolean) {
  const [result, setResult] = useState<ChatHistoryRead>({status: 'idle'});
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  useEffect(
    () =>
      subscribeOmiBackendSessionInvalidated(() => {
        epoch.current++;
        setResult(previous =>
          previous.status === 'idle'
            ? previous
            : {
                status: 'error',
                error: chatHistoryErrorCopy({
                  code: 'OMI_HTTP_UNAUTHORIZED',
                }),
              },
        );
      }),
    [],
  );
  useEffect(() => {
    const current = ++epoch.current;
    let alive = true;
    if (!active) {
      setResult({status: 'idle'});
      return () => {
        alive = false;
      };
    }
    setResult({status: 'loading'});
    const load = async () => {
      try {
        if (omiBackend == null) {
          throw new Error('Native transport unavailable');
        }
        const messages = await loadChatHistory(omiBackend);
        if (!alive || epoch.current !== current) {
          return;
        }
        setResult({status: 'loaded', messages});
      } catch (error) {
        if (alive && epoch.current === current) {
          setResult({status: 'error', error: chatHistoryErrorCopy(error)});
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
    reload: () => setReload(value => value + 1),
  };
}
