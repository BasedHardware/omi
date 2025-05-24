import { useState, useRef, useEffect } from 'react';

export function useChatUI() {
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showDevicePopup, setShowDevicePopup] = useState(false);
  const [userMessageCount, setUserMessageCount] = useState(0);
  const [inputText, setInputText] = useState('');

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      const scrollArea = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollArea) {
        scrollArea.scrollTop = scrollArea.scrollHeight;
      }
    }
  };

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

  return {
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
    scrollToBottom
  };
}