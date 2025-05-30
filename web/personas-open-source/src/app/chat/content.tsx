'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { auth } from '@/lib/firebase';
import { Message } from '@/types/chat';
import { Mixpanel } from '@/lib/mixpanel';
import { useChat } from './_hooks/use-chat';
import { useChatUI } from './_hooks/use-chat-ui';
import { ChatHeader } from './_components/chat-header';
import { ChatMessages } from './_components/chat-messages';
import { ChatInput } from './_components/chat-input';
import { LoginPrompt } from './_components/login-prompt';
import { SettingsDialog } from './_components/settings-dialog';
import { DevicePopup } from './_components/device-popup';

export function ChatContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const botId = searchParams.get('id');

  const {
    botData,
    messages,
    isLoading,
    typingMessage,
    setMessages,
    sendMessage,
    resetChat
    } = useChat(botId);

  const {
    showLoginPrompt,
    showSettingsDialog,
    showDevicePopup,
    userMessageCount,
    inputText,
    scrollRef,
    inputRef,
    setShowLoginPrompt,
    setShowSettingsDialog,
    setShowDevicePopup,
    setUserMessageCount,
    setInputText,
  } = useChatUI();

  const botName = botData?.name || 'Omi';
  const botImage = botData?.avatar || botData?.image || '/omi-avatar.svg';
  const username = botData?.username || '';
  const botCategory = botData?.category || '';

  const getStoreUrl = useMemo(() => {
    const currentUrl = typeof window !== 'undefined' ? window.location.search : '';
    return `https://www.omi.me/pages/product?ref=personas${currentUrl ? `&${currentUrl.substring(1)}` : ''}`;
  }, []);

  const handleSendMessage = useCallback(async () => {
    if (!inputText.trim() || isLoading) return;

    const newUserMessageCount = userMessageCount + 1;
    setUserMessageCount(newUserMessageCount);

    Mixpanel.track('Message Sent', {
      bot_name: botName,
      bot_id: botId,
      message_count: newUserMessageCount,
      is_authenticated: !!auth.currentUser,
      timestamp: new Date().toISOString()
    });

    if (!auth.currentUser && newUserMessageCount >= 3) {
      setShowLoginPrompt(true);
      return;
    }

    const userMessage: Message = {
      id: Date.now(),
      text: inputText,
      sender: 'user',
      type: 'text',
      status: 'sent'
    };

    setMessages(prev => [...prev, userMessage]);
    setInputText('');

    try {
      const response = await sendMessage(inputText);
      
      if (response) {
        setMessages(prev => [...prev, {
          id: Date.now(),
          text: response,
          sender: 'omi',
          type: 'text',
          status: 'received'
        }]);

        Mixpanel.track('Message Received', {
          bot_name: botName,
          bot_id: botId,
          message_length: response.length,
          is_authenticated: !!auth.currentUser,
          timestamp: new Date().toISOString()
        });
      }
    } catch (error: any) {
      console.error('Error:', error);
      Mixpanel.track('Message Error', {
        bot_name: botName,
        bot_id: botId,
        error: error.toString(),
        is_authenticated: !!auth.currentUser,
        timestamp: new Date().toISOString()
      });
    }
  }, [inputText, isLoading, userMessageCount, botName, botId, sendMessage]);

  const handleKeyPress = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  }, [handleSendMessage]);

  const handleResetChat = useCallback(async () => {
    await resetChat();
    setShowSettingsDialog(false);
  }, [resetChat]);

  return (
    <div className="flex flex-col h-screen bg-zinc-900 text-white">
      <ChatHeader
        botName={botName}
        botImage={botImage}
        username={username}
        botCategory={botCategory}
        onBackClick={() => router.push('/')}
        onSettingsClick={() => setShowSettingsDialog(true)}
        getStoreUrl={getStoreUrl}
      />

      <div className="text-center py-2 text-xs text-gray-500">
        Today {new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
      </div>

      <ChatMessages
        messages={messages}
        typingMessage={typingMessage}
        botName={botName}
        botImage={botImage}
        scrollRef={scrollRef}
      />

      <ChatInput
        inputRef={inputRef}
        inputText={inputText}
        isLoading={isLoading}
        onInputChange={setInputText}
        onSendMessage={handleSendMessage}
        onKeyPress={handleKeyPress}
        getStoreUrl={getStoreUrl}
      />

      {showLoginPrompt && (
        <LoginPrompt
          messages={messages}
          botName={botName}
          botImage={botImage}
          botId={botId || ''}
          onLoginSuccess={() => setShowLoginPrompt(false)}
        />
      )}

      <SettingsDialog
        isOpen={showSettingsDialog}
        onClose={() => setShowSettingsDialog(false)}
        onReset={handleResetChat}
      />

      <DevicePopup
        isVisible={showDevicePopup}
        onClose={() => setShowDevicePopup(false)}
      />
    </div>
  );
}