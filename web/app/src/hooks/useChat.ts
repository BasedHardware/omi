'use client';

import { useState, useCallback, useRef } from 'react';
import {
  getMessages,
  sendMessageStream,
  clearMessages as clearMessagesApi,
} from '@/lib/api';
import type { ServerMessage, MessageChunk } from '@/types/conversation';

interface UseChatOptions {
  appId?: string;
}

interface UseChatReturn {
  messages: ServerMessage[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingText: string;
  currentThinking: string;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  clearHistory: () => Promise<void>;
  loadHistory: () => Promise<void>;
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { appId } = options;

  const [messages, setMessages] = useState<ServerMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [currentThinking, setCurrentThinking] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Track if we've loaded history
  const historyLoadedRef = useRef(false);

  /**
   * Load message history from server
   */
  const loadHistory = useCallback(async () => {
    if (historyLoadedRef.current) return;

    setIsLoading(true);
    setError(null);

    try {
      const history = await getMessages(appId);
      setMessages(history);
      historyLoadedRef.current = true;
    } catch (err) {
      console.error('Failed to load message history:', err);
      setError('Failed to load message history');
    } finally {
      setIsLoading(false);
    }
  }, [appId]);

  /**
   * Send a message and handle streaming response
   */
  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isStreaming) return;

    setError(null);
    setIsStreaming(true);
    setStreamingText('');
    setCurrentThinking('');

    // Add user message to the list immediately (optimistic update)
    const userMessage: ServerMessage = {
      id: `temp-${Date.now()}`,
      created_at: new Date().toISOString(),
      text: text.trim(),
      sender: 'human',
      type: 'text',
      from_integration: false,
      files: [],
      memories: [],
      ask_for_nps: false,
    };

    setMessages((prev) => [...prev, userMessage]);

    let accumulatedText = '';

    try {
      await sendMessageStream(
        text.trim(),
        (chunk: MessageChunk) => {
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
              if (chunk.message) {
                console.log('Related memory:', chunk.message);
              }
              break;

            case 'error':
              setError(chunk.text);
              break;
          }
        },
        { appId }
      );
    } catch (err) {
      console.error('Failed to send message:', err);
      setError(err instanceof Error ? err.message : 'Failed to send message');

      // If we have accumulated text, add it as a partial message
      if (accumulatedText) {
        const partialMessage: ServerMessage = {
          id: `error-${Date.now()}`,
          created_at: new Date().toISOString(),
          text: accumulatedText + '\n\n[Message interrupted]',
          sender: 'ai',
          type: 'text',
          from_integration: false,
          files: [],
          memories: [],
          ask_for_nps: false,
        };
        setMessages((prev) => [...prev, partialMessage]);
      }
    } finally {
      setIsStreaming(false);
      setStreamingText('');
    }
  }, [appId, isStreaming]);

  /**
   * Clear all message history
   */
  const clearHistory = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      await clearMessagesApi(appId);
      setMessages([]);
      historyLoadedRef.current = false;
    } catch (err) {
      console.error('Failed to clear messages:', err);
      setError('Failed to clear message history');
    } finally {
      setIsLoading(false);
    }
  }, [appId]);

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
  };
}
