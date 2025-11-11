'use client';

import { Fragment, useState, useRef, useEffect } from 'react';
import Tabs from '../tabs';
import Summary from './sumary';
import Transcription from '../transcript/transcription';
import Chat from '../chat/chat';
import { Memory } from '@/src/types/memory.types';

interface MemoryWithTabsProps {
  memory: Memory;
}

export default function MemoryWithTabs({ memory }: MemoryWithTabsProps) {
  const [currentTab, setCurrentTab] = useState('sum');
  const clearChatRef = useRef<(() => void) | null>(null);
  const [hasMessages, setHasMessages] = useState(false);

  const handleClearChatRef = (clearFn: () => void) => {
    clearChatRef.current = clearFn;
  };

  const handleNewChat = () => {
    if (clearChatRef.current) {
      clearChatRef.current();
    }
  };

  // Prevent page scrolling when chat tab is active
  useEffect(() => {
    if (currentTab === 'chat') {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }

    return () => {
      document.body.style.overflow = '';
    };
  }, [currentTab]);

  return (
    <Fragment>
      <Tabs
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        onNewChat={handleNewChat}
        showNewChat={hasMessages}
      />
      <div className="">
        {currentTab === 'sum' ? (
          <Summary memory={memory} />
        ) : currentTab === 'trs' ? (
          <Transcription
            transcript={memory.transcript_segments}
            externalData={memory.external_data}
            people={memory.people}
          />
        ) : (
          <Chat
            transcript={memory.transcript_segments}
            onClearChatRef={handleClearChatRef}
            onMessagesChange={setHasMessages}
          />
        )}
      </div>
    </Fragment>
  );
}
