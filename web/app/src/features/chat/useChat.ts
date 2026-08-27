'use client';

import { useCallback, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import {
  getMessages,
  sendMessageStream,
  clearMessages as clearMessagesApi,
  saveRealtimeMessage,
} from '@/features/chat/api';
import type { ClientMessage, MessageChunk, MessageFile } from '@/types/conversation';
import type { ChatContextInfo } from '@/features/chat/ui/ChatContext';
import { useRequestOwner } from '@/hooks/useRequestOwner';

interface UseChatOptions {
  appId?: string;
  /**
   * Which chat session to read. `null` is the default shared thread every
   * client sees through `/v2/messages`; an id targets that one thread.
   */
  chatSessionId?: string | null;
}

interface UseChatReturn {
  messages: ClientMessage[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingText: string;
  currentThinking: string;
  error: string | null;
  sendMessage: (
    text: string,
    fileIds?: string[],
    context?: ChatContextInfo | null,
    optimisticFiles?: MessageFile[],
  ) => Promise<void>;
  clearHistory: () => Promise<void>;
  loadHistory: () => Promise<void>;
  appendRealtimeExchange: (humanText: string, aiText: string) => Promise<void>;
}

export function createChatStore() {
  const messages = createSignal<ClientMessage[]>([]);
  const isLoading = createSignal(false);
  const isStreaming = createSignal(false);
  const streamingText = createSignal('');
  const currentThinking = createSignal('');
  const error = createSignal<string | null>(null);
  let historyLoadedKey: string | null = null;

  return {
    messages,
    isLoading,
    isStreaming,
    streamingText,
    currentThinking,
    error,
    getHistoryLoadedKey: () => historyLoadedKey,
    setHistoryLoadedKey: (key: string | null) => {
      historyLoadedKey = key;
    },
  };
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { appId, chatSessionId = null } = options;
  const store = useMemo(() => createChatStore(), [appId, chatSessionId]);
  const claimRequest = useRequestOwner(`${appId ?? ''}||${chatSessionId ?? ''}`);

  const messages = useSignalValue(store.messages);
  const isLoading = useSignalValue(store.isLoading);
  const isStreaming = useSignalValue(store.isStreaming);
  const streamingText = useSignalValue(store.streamingText);
  const currentThinking = useSignalValue(store.currentThinking);
  const error = useSignalValue(store.error);

  const loadHistory = useCallback(async () => {
    const targetKey = `${appId ?? ''}||${chatSessionId ?? ''}`;
    if (store.getHistoryLoadedKey() === targetKey) return;

    const isCurrent = claimRequest();
    store.isLoading.set(true);
    store.error.set(null);

    try {
      const history = await getMessages(appId, chatSessionId);
      if (!isCurrent()) return;
      store.messages.set([...history].reverse());
      store.setHistoryLoadedKey(targetKey);
    } catch (err) {
      if (!isCurrent()) return;
      console.error('Failed to load message history:', err);
      store.error.set('Failed to load message history');
    } finally {
      if (isCurrent()) store.isLoading.set(false);
    }
  }, [appId, chatSessionId, claimRequest, store]);

  const sendMessage = useCallback(
    async (
      text: string,
      fileIds?: string[],
      context?: ChatContextInfo | null,
      optimisticFiles?: MessageFile[],
    ) => {
      if ((!text.trim() && !fileIds?.length) || store.isStreaming.peek()) return;

      const isCurrent = claimRequest();
      store.error.set(null);
      store.isStreaming.set(true);
      store.streamingText.set('');
      store.currentThinking.set('');

      const createdAt = new Date().toISOString();
      const uploadedFilesById = new Map(
        optimisticFiles?.map((file) => [file.id, file]) ?? [],
      );
      const userMessage: ClientMessage = {
        id: `temp-${Date.now()}`,
        created_at: createdAt,
        text: text.trim(),
        sender: 'human',
        type: 'text',
        from_external_integration: false,
        files: (fileIds ?? []).map(
          (id) =>
            uploadedFilesById.get(id) ?? {
              id,
              created_at: createdAt,
              mime_type: 'application/octet-stream',
              name: 'Attached file',
              openai_file_id: '',
            },
        ),
        memories: [],
        ask_for_nps: false,
      };

      store.messages.set((prev) => [...prev, userMessage]);

      let accumulatedText = '';

      try {
        await sendMessageStream(
          text.trim(),
          (chunk: MessageChunk) => {
            if (!isCurrent()) return;
            switch (chunk.type) {
              case 'think':
                store.currentThinking.set((prev) => prev + chunk.text);
                break;

              case 'data':
                accumulatedText += chunk.text;
                store.streamingText.set(accumulatedText);
                break;

              case 'done':
                if (chunk.message) {
                  store.messages.set((prev) => [...prev, chunk.message!]);
                }
                store.streamingText.set('');
                store.currentThinking.set('');
                break;

              case 'message':
                break;

              case 'error':
                store.error.set(chunk.text);
                break;
            }
          },
          { appId, chatSessionId, fileIds, context: context || null },
        );
      } catch (err) {
        if (!isCurrent()) return;
        console.error('Failed to send message:', err);
        store.error.set(err instanceof Error ? err.message : 'Failed to send message');

        if (accumulatedText) {
          const partialMessage: ClientMessage = {
            id: `error-${Date.now()}`,
            created_at: new Date().toISOString(),
            text: accumulatedText + '\n\n[Message interrupted]',
            sender: 'ai',
            type: 'text',
            from_external_integration: false,
            files: [],
            memories: [],
            ask_for_nps: false,
          };
          store.messages.set((prev) => [...prev, partialMessage]);
        }
      } finally {
        if (isCurrent()) {
          store.isStreaming.set(false);
          store.streamingText.set('');
        }
      }
    },
    [appId, chatSessionId, claimRequest, store],
  );

  const clearHistory = useCallback(async () => {
    const isCurrent = claimRequest();
    store.isLoading.set(true);
    store.error.set(null);

    try {
      await clearMessagesApi(appId, chatSessionId);
      if (!isCurrent()) return;
      store.messages.set([]);
      store.setHistoryLoadedKey(null);
    } catch (err) {
      if (!isCurrent()) return;
      console.error('Failed to clear messages:', err);
      store.error.set('Failed to clear message history');
    } finally {
      if (isCurrent()) store.isLoading.set(false);
    }
  }, [appId, chatSessionId, claimRequest, store]);

  const appendRealtimeExchange = useCallback(
    async (humanText: string, aiText: string) => {
      const isCurrent = claimRequest();
      const entries = [
        { text: humanText.trim(), sender: 'human' as const },
        { text: aiText.trim(), sender: 'ai' as const },
      ].filter((entry) => entry.text);
      if (entries.length === 0) return;

      const optimistic = entries.map((entry) => ({
        id: crypto.randomUUID(),
        created_at: new Date().toISOString(),
        text: entry.text,
        sender: entry.sender,
        type: 'text' as const,
        from_external_integration: false,
        files: [],
        memories: [],
        ask_for_nps: false,
        message_source: 'realtime_voice',
        chat_session_id: chatSessionId,
        app_id: appId,
      }));

      store.messages.set((current) => [...current, ...optimistic]);
      store.error.set(null);

      try {
        for (const message of optimistic) {
          await saveRealtimeMessage({
            text: message.text,
            sender: message.sender,
            clientMessageId: message.id,
            appId,
            sessionId: chatSessionId,
          });
        }
      } catch (err) {
        console.error('Failed to save live conversation:', err);
        if (isCurrent()) store.error.set('Live conversation was not saved to chat history');
        throw err;
      }
    },
    [appId, chatSessionId, claimRequest, store],
  );

  return {
    messages,
    isLoading,
    isStreaming,
    streamingText,
    currentThinking,
    error,
    sendMessage,
    clearHistory,
    loadHistory,
    appendRealtimeExchange,
  };
}
