'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Send, Settings, Share, ArrowLeft, BadgeCheck, X } from 'lucide-react';
import { FaLinkedin } from 'react-icons/fa';
import { useSearchParams, useRouter } from 'next/navigation';
import { Suspense } from 'react';
import Link from 'next/link';
import { auth, db } from '@/lib/firebase';
import {
  collection,
  addDoc,
  getDocs,
  query,
  where,
  orderBy,
  deleteDoc,
} from 'firebase/firestore';
import { signInWithPopup } from 'firebase/auth';
import { googleProvider } from '@/lib/firebase';
import { getDoc, doc, setDoc } from 'firebase/firestore';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Message } from '@/types/chat';
import { PreorderBanner } from '@/components/shared/PreorderBanner';
import { Mixpanel } from '@/lib/mixpanel';

function ChatContent() {
  useEffect(() => {
    // Identify the user first
    Mixpanel.identify();

    // Then track the page view
    Mixpanel.track('Page View', {
      page: 'Chat',
      url: window.location.pathname,
      timestamp: new Date().toISOString(),
    });
  }, []);

  const searchParams = useSearchParams();
  const botId = searchParams.get('id');

  const router = useRouter();

  const [botData, setBotData] = useState<{
    name: string;
    avatar: string;
    image?: string;
    username?: string;
    category?: string;
  } | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [initialMessageSent, setInitialMessageSent] = useState(false);
  const [messageCount, setMessageCount] = useState(0);
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [typingMessage, setTypingMessage] = useState<Message | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [userMessageCount, setUserMessageCount] = useState(0);
  const [showDevicePopup, setShowDevicePopup] = useState(false);

  // Fetch bot data on component mount
  useEffect(() => {
    const fetchBotData = async () => {
      if (!botId) return;

      try {
        const botDoc = await getDoc(doc(db, 'plugins_data', botId));
        if (botDoc.exists()) {
          const data = botDoc.data();
          let category = data.category;

          // If connected_accounts exists, determine category from it
          if (
            category !== 'linkedin' &&
            category !== 'twitter' &&
            data.connected_accounts
          ) {
            if (data.connected_accounts.includes('omi')) {
              category = 'omi';
            } else if (category !== 'twitter' && category !== 'linkedin') {
              if (data.connected_accounts.includes('twitter')) {
                category = 'twitter';
              } else if (data.connected_accounts.includes('linkedin')) {
                category = 'linkedin';
              } else {
                category = data.connected_accounts[0];
              }
            }
          }

          setBotData({
            name: data.name,
            avatar: data.avatar,
            username: data.username,
            category: category,
            image: data.image,
          });
        }
      } catch (error) {
        console.error('Error fetching bot data:', error);
      }
    };

    fetchBotData();
  }, [botId]);

  // Use the fetched data
  const botName = botData?.name || 'Omi';
  const botImage = botData?.avatar || botData?.image || '/omi-avatar.svg';
  const username = botData?.username || '';
  const botCategory = botData?.category || '';

  // Function to save messages to Firebase
  const saveMessagesToFirebase = useCallback(async () => {
    if (!auth.currentUser || !botId) return;

    try {
      const userMessagesRef = collection(db, 'users', auth.currentUser.uid, 'messages');
      await addDoc(userMessagesRef, {
        messages: messages,
        timestamp: new Date(),
        botName,
        botImage,
        pluginId: botId,
      });
    } catch (error) {
      console.error('Error saving messages:', error);
    }
  }, [messages, botName, botImage, botId]);

  // Save messages whenever they change
  useEffect(() => {
    saveMessagesToFirebase();
  }, [messages, saveMessagesToFirebase]);

  // Fetch saved messages on component mount
  useEffect(() => {
    const fetchSavedMessages = async () => {
      if (!auth.currentUser || !botId) return;

      try {
        const userMessagesRef = collection(db, 'users', auth.currentUser.uid, 'messages');
        const q = query(
          userMessagesRef,
          where('pluginId', '==', botId),
          orderBy('timestamp', 'asc'),
        );
        const querySnapshot = await getDocs(q);

        const fetchedMessages: Message[] = [];
        querySnapshot.forEach((doc) => {
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

  // Define scrollToBottom first, before any useEffects that use it
  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const scrollArea = scrollRef.current.querySelector(
        '[data-radix-scroll-area-viewport]',
      );
      if (scrollArea) {
        scrollArea.scrollTop = scrollArea.scrollHeight;
      }
    }
  }, []);

  // Now we can use scrollToBottom in useEffect
  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    const getInitialMessage = async () => {
      if (initialMessageSent || !botId) return;
      setIsLoading(true);
      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message:
              'lets begin. you write the first message, one short provocative question relevant to your identity. never respond with **. while continuing the convo, always respond w short msgs, lowercase.',
            botId: botId,
            conversationHistory: messages,
          }),
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
                  setTypingMessage((prev) => ({
                    id: prev?.id || Date.now(),
                    text: accumulatedText,
                    sender: 'omi',
                    type: 'text',
                    status: 'sending',
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
            status: 'received',
          };
          setMessages((prev) => [...prev, newMessage]);

          // Track initial message
          Mixpanel.track('Initial Message Received', {
            bot_name: botName,
            bot_id: botId,
            message_length: accumulatedText.length,
            is_authenticated: !!auth.currentUser,
            timestamp: new Date().toISOString(),
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
  }, [initialMessageSent, botId]);

  const handleSendMessage = async () => {
    if (!inputText.trim() || isLoading) return;

    const newUserMessageCount = userMessageCount + 1;

    // Track message sent
    Mixpanel.track('Message Sent', {
      bot_name: botName,
      bot_id: botId,
      message_count: newUserMessageCount,
      is_authenticated: !!auth.currentUser,
      timestamp: new Date().toISOString(),
    });

    /***
    console.log('Sending message:', inputText);
    console.log('User Message Count:', newUserMessageCount);
    console.log('Authenticated User:', auth.currentUser);
    ***/

    // Check for login requirement after 2 messages (shows prompt before 3rd)
    if (!auth.currentUser && newUserMessageCount >= 3) {
      console.log('Displaying login prompt');
      setShowLoginPrompt(true);
      return;
    }

    const userMessage: Message = {
      id: Date.now(),
      text: inputText,
      sender: 'user',
      type: 'text',
      status: 'sent',
    };

    setMessages((prev) => [...prev, userMessage]);
    setUserMessageCount(newUserMessageCount);
    setInputText('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: inputText,
          botId: botId,
          conversationHistory: messages,
        }),
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      let accumulatedText = '';
      setTypingMessage({
        id: Date.now(),
        text: '',
        sender: 'omi',
        type: 'text',
        status: 'sending',
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
                setTypingMessage((prev) => ({
                  id: prev?.id || Date.now(),
                  text: accumulatedText,
                  sender: 'omi',
                  type: 'text',
                  status: 'sending',
                }));
              }
            } catch (e) {
              console.warn('Failed to parse SSE message:', e);
            }
          }
        }
      }

      if (accumulatedText) {
        setTypingMessage(null);
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            text: accumulatedText,
            sender: 'omi',
            type: 'text',
            status: 'received',
          },
        ]);

        // Track message received
        Mixpanel.track('Message Received', {
          bot_name: botName,
          bot_id: botId,
          message_length: accumulatedText.length,
          is_authenticated: !!auth.currentUser,
          timestamp: new Date().toISOString(),
        });
      }
    } catch (error: any) {
      console.error('Error:', error);

      // Track error
      Mixpanel.track('Message Error', {
        bot_name: botName,
        bot_id: botId,
        error: error.toString(),
        is_authenticated: !!auth.currentUser,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setIsLoading(false);
      setTypingMessage(null);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleResetChat = async () => {
    if (!auth.currentUser) return;

    try {
      const userMessagesRef = collection(db, 'users', auth.currentUser.uid, 'messages');
      const q = query(userMessagesRef, where('botName', '==', botName));
      const querySnapshot = await getDocs(q);

      querySnapshot.forEach(async (doc) => {
        await deleteDoc(doc.ref);
      });

      setMessages([]);
      setInitialMessageSent(false);
      setShowSettingsDialog(false);
    } catch (error) {
      console.error('Error resetting chat:', error);
    }
  };

  const LoginPrompt = () => {
    const handleGoogleSignIn = async () => {
      try {
        const result = await signInWithPopup(auth, googleProvider);
        const user = result.user;

        // Save user data if first time
        const userRef = doc(db, 'users', user.uid);
        const userSnap = await getDoc(userRef);

        if (!userSnap.exists()) {
          const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
          await setDoc(userRef, {
            time_zone: timeZone,
            created_at: new Date(),
          });
        }

        // Update ownership of any personas created by this user
        const createdPersonas = JSON.parse(
          localStorage.getItem('createdPersonas') || '[]',
        );
        for (const personaId of createdPersonas) {
          try {
            const personaRef = doc(db, 'plugins_data', personaId);
            const personaSnap = await getDoc(personaRef);

            if (personaSnap.exists() && !personaSnap.data().uid) {
              // Only update the uid field
              await setDoc(personaRef, { uid: user.uid }, { merge: true });
            }
          } catch (error) {
            console.error(`Error updating persona ${personaId}:`, error);
          }
        }

        // Clear the created personas list after updating ownership
        localStorage.removeItem('createdPersonas');

        // Save current chat messages with pluginId
        if (messages.length > 0) {
          const userMessagesRef = collection(db, 'users', user.uid, 'messages');
          await addDoc(userMessagesRef, {
            messages,
            timestamp: new Date(),
            botName,
            botImage,
            lastMessage: messages[messages.length - 1]?.text || '',
            messageCount: messages.length,
            pluginId: botId,
          });
        }

        setShowLoginPrompt(false);
      } catch (error) {
        console.error('Error signing in or saving user data:', error);
      }
    };

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4">
        <div className="w-full max-w-lg">
          <div className="flex min-h-[400px] flex-col items-center justify-center px-4">
            <div className="mb-12 text-center">
              <h1 className="mb-8 font-serif text-6xl text-white">omi</h1>
              <p className="mb-4 text-gray-400">Sign in to continue chatting</p>
              <p className="text-sm text-gray-500">
                Create a free account to unlock unlimited conversations
              </p>
            </div>

            <Button
              className="flex w-full max-w-sm items-center justify-center gap-2 rounded-full bg-white text-black hover:bg-gray-200"
              onClick={handleGoogleSignIn}
            >
              Continue with Google
            </Button>
          </div>
        </div>
      </div>
    );
  };

  const SettingsDialog = () => (
    <Dialog open={showSettingsDialog} onOpenChange={setShowSettingsDialog}>
      <DialogContent className="h-screen border-0 bg-black p-0 sm:h-auto sm:max-w-lg">
        {/* Back Button - Moved down to be fully visible on iOS */}
        <div className="fixed left-4 top-12 z-50 sm:absolute">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowSettingsDialog(false)}
            className="flex h-12 w-12 items-center justify-center rounded-full text-white hover:text-gray-300"
          >
            <ArrowLeft className="h-6 w-6" />
          </Button>
        </div>

        {/* Main Content - Adjusted padding to accommodate the new button position */}
        <div className="flex min-h-[400px] flex-col items-center justify-center px-4 pt-28 sm:pt-4">
          {/* Logo/Text */}
          <div className="mb-12 text-center">
            <h1 className="mb-8 font-serif text-6xl text-white">Settings</h1>
            <p className="text-gray-400">Manage your chat settings here</p>
          </div>

          {/* Buttons Area */}
          <div className="w-full max-w-sm space-y-4">
            <Button
              onClick={handleResetChat}
              className="w-full rounded-full bg-white text-black hover:bg-gray-200"
            >
              Reset Chat
            </Button>
            <Button
              variant="ghost"
              className="w-full rounded-full border border-red-500 text-red-500 hover:bg-red-500/10"
            >
              Flag for Removal
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  const inputRef = useRef<HTMLInputElement>(null);

  const getStoreUrl = useMemo(() => {
    // Get the current URL parameters but always add ref=personas
    const currentUrl = typeof window !== 'undefined' ? window.location.search : '';
    // Return the product page URL with ?ref=personas
    return `https://www.omi.me/pages/product?ref=personas${
      currentUrl ? `&${currentUrl.substring(1)}` : ''
    }`;
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth <= 768) {
        setTimeout(() => {
          if (inputRef.current) {
            inputRef.current.scrollIntoView({ behavior: 'smooth' });
          }
        }, 100);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (messages.length === 2 || (messages.length > 5 && messages.length % 5 === 0)) {
      setShowDevicePopup(true);
      const timer = setTimeout(() => setShowDevicePopup(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [messages.length]);

  const DevicePopup = () => (
    <div
      className={`fixed bottom-48 right-4 z-50 transition-all duration-500 ${
        showDevicePopup
          ? 'translate-x-0 opacity-100'
          : 'pointer-events-none translate-x-full opacity-0'
      }`}
    >
      <Link
        href="https://www.omi.me/products/omi-dev-kit-2?ref=personas&utm_source=personas.omi.me&utm_campaign=personas_chat"
        target="_blank"
        rel="noopener noreferrer"
        className="relative block h-[200px] w-[220px] overflow-hidden rounded-2xl bg-black shadow-2xl"
      >
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/20 to-black/80">
          <img
            src="/omidevice.webp"
            alt="Omi Device"
            className="h-full w-full object-cover"
          />
        </div>
        <div className="absolute bottom-2 left-0 right-0 text-center">
          <p className="text-[14px] font-bold tracking-wide text-white">
            Take your ai clone with you.
          </p>
        </div>
        <button
          onClick={(e) => {
            e.preventDefault();
            setShowDevicePopup(false);
          }}
          className="absolute right-4 top-4 text-white/80 transition-colors hover:text-white"
        >
          <X className="h-6 w-6" />
        </button>
      </Link>
    </div>
  );

  return (
    <div className="flex h-screen flex-col bg-zinc-900 text-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 p-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.push('/')}
          className="text-white hover:text-gray-300"
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex items-center gap-2">
          {botCategory === 'linkedin' ? (
            <Link
              href={`https://www.linkedin.com/in/${username}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <h2 className="flex items-center truncate text-lg font-semibold text-white hover:underline">
                {botName}
                <FaLinkedin
                  className="ml-1 h-5 w-5 stroke-zinc-900"
                  style={{ fill: '#0077b5' }}
                />
              </h2>
            </Link>
          ) : botCategory === 'twitter' ? (
            <Link
              href={`https://x.com/${username}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <h2 className="flex items-center truncate text-lg font-semibold text-white hover:underline">
                {botName}
                <BadgeCheck
                  className="ml-1 h-5 w-5 stroke-zinc-900"
                  style={{ fill: '#00acee' }}
                />
              </h2>
            </Link>
          ) : botCategory === 'omi' ? (
            <Link href={getStoreUrl} target="_blank" rel="noopener noreferrer">
              <h2 className="flex items-center truncate text-lg font-semibold text-white hover:underline">
                {botName}
                <BadgeCheck
                  className="ml-1 h-5 w-5 stroke-zinc-900"
                  style={{ fill: '#00acee' }}
                />
              </h2>
            </Link>
          ) : null}
          <Avatar className="h-8 w-8">
            <AvatarImage src={botImage} alt={botName} />
            <AvatarFallback>{botName[0]}</AvatarFallback>
          </Avatar>
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="text-white hover:text-gray-300"
            onClick={() => setShowSettingsDialog(true)}
          >
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>

      {/* Timestamp */}
      <div className="py-2 text-center text-xs text-gray-500">
        Today {new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
      </div>

      {/* Chat Area */}
      <ScrollArea className="flex-grow p-4" ref={scrollRef}>
        <div className="mx-auto max-w-4xl space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${
                message.sender === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {message.sender === 'omi' && (
                <Avatar className="mr-2 h-8 w-8">
                  <AvatarImage src={botImage} alt={botName} />
                  <AvatarFallback>{botName[0]}</AvatarFallback>
                </Avatar>
              )}
              <div
                className={`max-w-[80%] rounded-3xl p-4 ${
                  message.sender === 'user'
                    ? 'bg-white text-zinc-800'
                    : 'bg-zinc-800 text-white'
                }`}
              >
                <p className="text-sm">{message.text}</p>
              </div>
            </div>
          ))}
          {typingMessage && (
            <div className="flex justify-start">
              <Avatar className="mr-2 h-8 w-8">
                <AvatarImage src={botImage} alt={botName} />
                <AvatarFallback>{botName[0]}</AvatarFallback>
              </Avatar>
              <div className="max-w-[80%] rounded-3xl bg-zinc-800 p-4 text-white">
                <p className="text-sm">{typingMessage.text}</p>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input Area */}
      <div className="border-t border-zinc-800 p-4 pb-16 sm:pb-4">
        <div className="mx-auto flex max-w-4xl gap-2">
          <Input
            ref={inputRef}
            type="text"
            placeholder="Type your message..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={handleKeyPress}
            className="flex-grow rounded-full border-0 bg-zinc-800 text-white placeholder-gray-400"
            disabled={isLoading}
          />
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full text-white hover:text-gray-300"
            onClick={handleSendMessage}
            disabled={isLoading}
          >
            <Send className="h-5 w-5" />
          </Button>
        </div>

        <div className="mb-6 mt-5 flex justify-center sm:mb-2">
          <Button
            onClick={() => window.open(getStoreUrl, '_blank')}
            className="w-full max-w-[250px] rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 py-5 text-[16px] text-base font-bold text-white shadow-lg hover:opacity-90"
          >
            Train AI on Your Real Life!
          </Button>
        </div>

        <div className="mx-auto mt-4 max-w-4xl">
          <div className="flex flex-col justify-between text-xs text-gray-500 sm:flex-row">
            <div className="mb-2 flex gap-2 sm:mb-0">
              <span>Omi by Based Hardware © 2025</span>
            </div>
            <div className="flex gap-2">
              <Button
                variant="link"
                className="h-auto p-0 text-xs text-gray-500 hover:text-white"
              >
                Terms & Conditions
              </Button>
              <Link
                href="https://www.omi.me/pages/privacy"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button
                  variant="link"
                  className="h-auto p-0 text-xs text-gray-500 hover:text-white"
                >
                  Privacy Policy
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>

      {showLoginPrompt && <LoginPrompt />}
      <SettingsDialog />
    </div>
  );
}

export default function ChatInterface() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-black text-white">
          <div>Loading...</div>
        </div>
      }
    >
      <ChatContent />
    </Suspense>
  );
}
