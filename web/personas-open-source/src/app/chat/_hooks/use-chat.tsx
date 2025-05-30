'use client';

import { useState, useEffect } from 'react';
import { auth, db } from '@/lib/firebase';
import { collection, getDocs, query, where, orderBy, deleteDoc, doc, getDoc } from 'firebase/firestore';
import { Message } from '@/types/chat';
import { Mixpanel } from '@/lib/mixpanel';

export function useChat(botId: string | null) {
  const [botData, setBotData] = useState<{
    name: string;
    avatar: string;
    image?: string;
    username?: string;
    category?: string;
  } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [initialMessageSent, setInitialMessageSent] = useState(false);
  const [typingMessage, setTypingMessage] = useState<Message | null>(null);

  useEffect(() => {
    const fetchBotData = async () => {
      if (!botId) return;

      try {
        const botDoc = await getDoc(doc(db, 'plugins_data', botId));
        if (botDoc.exists()) {
          const data = botDoc.data();
          let category = data.category;
          
          if (category !== 'linkedin' && category !== 'twitter' && data.connected_accounts) {
            if (data.connected_accounts.includes('omi')) {
              category = 'omi';
            } 
            else if (category !== 'twitter' && category !== 'linkedin') {
              if (data.connected_accounts.includes('twitter')) {
                category = 'twitter';
              } else if (data.connected_accounts.includes('linkedin')) {
                category = 'linkedin';
              } 
              else {
                category = data.connected_accounts[0];
              }
            }
          }
          
          setBotData({
            name: data.name,
            avatar: data.avatar,
            username: data.username,
            category: category,
            image: data.image
          });
        }
      } catch (error) {
        console.error('Error fetching bot data:', error);
      }
    };

    fetchBotData();
  }, [botId]);

  useEffect(() => {
    const fetchSavedMessages = async () => {
      if (!auth.currentUser || !botId) return;

      try {
        const userMessagesRef = collection(db, 'users', auth.currentUser.uid, 'messages');
        const q = query(
          userMessagesRef,
          where('pluginId', '==', botId),
          orderBy('timestamp', 'asc')
        );
        const querySnapshot = await getDocs(q);

        const fetchedMessages: Message[] = [];
        querySnapshot.forEach(doc => {
          const data = doc.data();
          fetchedMessages.push(...data.messages);
        });

        setMessages(fetchedMessages);
      } catch (error) {
        console.error('Error fetching saved messages:', error);
      }
    };

    fetchSavedMessages();
  }, [auth.currentUser, botId]);

  useEffect(() => {
    const getInitialMessage = async () => {
      if (initialMessageSent || !botId) return;
      setIsLoading(true);
      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: "lets begin. you write the first message, one short provocative question relevant to your identity. never respond with **. while continuing the convo, always respond w short msgs, lowercase.",
            botId: botId,
            conversationHistory: messages
          })
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No reader available');

        let accumulatedText = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = new TextDecoder().decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') continue;

              try {
                const parsed = JSON.parse(data);
                if (parsed.text) {
                  accumulatedText += parsed.text;
                  setTypingMessage(prev => ({
                    id: prev?.id || Date.now(),
                    text: accumulatedText,
                    sender: 'omi',
                    type: 'text',
                    status: 'sending'
                  }));
                }
              } catch (e) {
                console.warn('Failed to parse SSE message:', e);
              }
            }
          }
        }

        setTypingMessage(null);
        if (accumulatedText) {
          const newMessage: Message = {
            id: Date.now(),
            text: accumulatedText,
            sender: 'omi',
            type: 'text',
            status: 'received'
          };
          setMessages(prev => [...prev, newMessage]);

          Mixpanel.track('Initial Message Received', {
            bot_name: botData?.name || 'Omi',
            bot_id: botId,
            message_length: accumulatedText.length,
            is_authenticated: !!auth.currentUser,
            timestamp: new Date().toISOString()
          });
        }

      } catch (error) {
        console.error('Error getting initial message:', error);
      } finally {
        setIsLoading(false);
        setInitialMessageSent(true);
      }
    };

    getInitialMessage();
  }, [initialMessageSent, botId, messages, botData?.name]);

  const sendMessage = async (inputText: string) => {
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: inputText,
          botId: botId,
          conversationHistory: messages
        })
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      let accumulatedText = '';
      setTypingMessage({
        id: Date.now(),
        text: '',
        sender: 'omi',
        type: 'text',
        status: 'sending'
      });

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = new TextDecoder().decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            try {
              const parsed = JSON.parse(data);
              if (parsed.text) {
                accumulatedText += parsed.text;
                setTypingMessage(prev => ({
                  id: prev?.id || Date.now(),
                  text: accumulatedText,
                  sender: 'omi',
                  type: 'text',
                  status: 'sending'
                }));
              }
            } catch (e) {
              console.warn('Failed to parse SSE message:', e);
            }
          }
        }
      }

      setTypingMessage(null);
      return accumulatedText;

    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  };

  const resetChat = async () => {
    if (!auth.currentUser || !botData?.name) return;

    try {
      const userMessagesRef = collection(db, 'users', auth.currentUser.uid, 'messages');
      const q = query(userMessagesRef, where('botName', '==', botData.name));
      const querySnapshot = await getDocs(q);

      querySnapshot.forEach(async (doc) => {
        await deleteDoc(doc.ref);
      });

      setMessages([]);
      setInitialMessageSent(false);
    } catch (error) {
      console.error('Error resetting chat:', error);
    }
  };

  return {
    botData,
    messages,
    isLoading,
    initialMessageSent,
    setInitialMessageSent,
    typingMessage,
    setMessages,
    sendMessage,
    resetChat
  };
}
