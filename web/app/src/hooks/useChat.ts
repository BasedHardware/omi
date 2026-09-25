'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  getMessages,
  sendMessageStream,
  clearMessages as clearMessagesApi,
  saveRealtimeMessage,
} from '@/lib/api';
import type { ClientMessage, MessageChunk, MessageFile } from '@/types/conversation';
import type { ChatContextInfo } from '@/components/chat/ChatContext';
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

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { appId, chatSessionId = null } = options;

  const [messages, setMessages] = useState<ClientMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [currentThinking, setCurrentThinking] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Track current app + session to detect changes
  const currentAppIdRef = useRef(appId);
  const currentSessionIdRef = useRef(chatSessionId);
  // Track if we've loaded history for the current app + session
  const historyLoadedRef = useRef<string | null>(null);

  // A load or a stream belongs to the thread it was started for. Switching
  // threads mid-flight must not let the previous thread's response land in the
  // newly-selected one.
  const claimRequest = useRequestOwner(`${appId ?? ''}||${chatSessionId ?? ''}`);

  // Reset state when the app or the selected session changes. Switching threads
  // must clear the transcript: leaving the previous session's messages on
  // screen reads as though they belong to the newly-selected chat. The
  // transient stream state goes with it, for the same reason.
  useEffect(() => {
    if (
      currentAppIdRef.current !== appId ||
      currentSessionIdRef.current !== chatSessionId
    ) {
      currentAppIdRef.current = appId;
      currentSessionIdRef.current = chatSessionId;
      historyLoadedRef.current = null;
      setMessages([]);
      setError(null);
      setStreamingText('');
      setCurrentThinking('');
      setIsStreaming(false);
      setIsLoading(false);
    }
  }, [appId, chatSessionId]);

  /**
   * Load message history from server
   */
  const loadHistory = useCallback(async () => {
    const targetKey = `${appId ?? ''}||${chatSessionId ?? ''}`;
    if (historyLoadedRef.current === targetKey) return;

    const isCurrent = claimRequest();
    setIsLoading(true);
    setError(null);

    try {
      const history = await getMessages(appId, chatSessionId);
      if (!isCurrent()) return;
      setMessages([...history].reverse());
      historyLoadedRef.current = targetKey;
    } catch (err) {
      if (!isCurrent()) return;
      console.error('Failed to load message history:', err);
      setError('Failed to load message history');
    } finally {
      if (isCurrent()) setIsLoading(false);
    }
  }, [appId, chatSessionId, claimRequest]);

  /**
   * Send a message and handle streaming response
   */
  const sendMessage = useCallback(
    async (
      text: string,
      fileIds?: string[],
      context?: ChatContextInfo | null,
      optimisticFiles?: MessageFile[],
    ) => {
      if ((!text.trim() && !fileIds?.length) || isStreaming) return;

      const isCurrent = claimRequest();
      setError(null);
      setIsStreaming(true);
      setStreamingText('');
      setCurrentThinking('');

      // Add user message to the list immediately (optimistic update).
      // Client-only fields (`ask_for_nps`) live on ClientMessage; backend REST
      // authority for messages is the generated `Message` schema.
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

      setMessages((prev) => [...prev, userMessage]);

      let accumulatedText = '';

      try {
        await sendMessageStream(
          text.trim(),
          (chunk: MessageChunk) => {
            // Chunks that arrive after the reader moved to another thread
            // belong to the thread they were requested for, not this one.
            if (!isCurrent()) return;
            switch (chunk.type) {
              case 'think':
                setCurrentThinking((prev) => prev + chunk.text);
                break;

              case 'data':
                accumulatedText += chunk.text;
                setStreamingText(accumulatedText);
                break;

              case 'done':
                // Replace streaming text with final message
                if (chunk.message) {
                  setMessages((prev) => [...prev, chunk.message!]);
                }
                setStreamingText('');
                setCurrentThinking('');
                break;

              case 'message':
                // Handle related memory messages if needed
                // chunk.message contains related memory data
                break;

              case 'error':
                setError(chunk.text);
                break;
            }
          },
          { appId, chatSessionId, fileIds, context: context || null },
        );
      } catch (err) {
        if (!isCurrent()) return;
        console.error('Failed to send message:', err);
        setError(err instanceof Error ? err.message : 'Failed to send message');

        // If we have accumulated text, add it as a partial message
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
          setMessages((prev) => [...prev, partialMessage]);
        }
      } finally {
        if (isCurrent()) {
          setIsStreaming(false);
          setStreamingText('');
        }
      }
    },
    [appId, chatSessionId, isStreaming, claimRequest],
  );

  /**
   * Clear all message history
   */
  const clearHistory = useCallback(async () => {
    const isCurrent = claimRequest();
    setIsLoading(true);
    setError(null);

    try {
      await clearMessagesApi(appId, chatSessionId);
      if (!isCurrent()) return;
      setMessages([]);
      historyLoadedRef.current = null;
    } catch (err) {
      if (!isCurrent()) return;
      console.error('Failed to clear messages:', err);
      setError('Failed to clear message history');
    } finally {
      if (isCurrent()) setIsLoading(false);
    }
  }, [appId, chatSessionId, claimRequest]);

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

      setMessages((current) => [...current, ...optimistic]);
      setError(null);

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
        if (isCurrent()) setError('Live conversation was not saved to chat history');
        throw err;
      }
    },
    [appId, chatSessionId, claimRequest],
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
