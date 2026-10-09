'use client';

import { Fragment, useState, useRef } from 'react';
import Tabs from '../tabs';
import Summary from './sumary';
import Transcription from '../transcript/transcription';
import Chat from '../chat/chat';
import { Memory, SharedScreenshotsResult } from '@/src/types/memory.types';

interface MemoryWithTabsProps {
  memory: Memory;
  screenshots?: SharedScreenshotsResult | null;
}

export default function MemoryWithTabs({
  memory,
  screenshots = null,
}: MemoryWithTabsProps) {
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

  // No longer needed - chat tab handles its own layout
  // useEffect(() => {
  //   if (currentTab === 'chat') {
  //     document.body.style.overflow = 'hidden';
  //   } else {
  //     document.body.style.overflow = '';
  //   }

  //   return () => {
  //     document.body.style.overflow = '';
  //   };
  // }, [currentTab]);

  return (
    <Fragment>
      <Tabs
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        onNewChat={handleNewChat}
        showNewChat={hasMessages}
      />
      <div>
        <div
          className="sn-tabpanel"
          style={{ display: currentTab === 'sum' ? 'block' : 'none' }}
        >
          <Summary memory={memory} screenshots={screenshots} />
        </div>
        <div
          className="sn-tabpanel"
          style={{ display: currentTab === 'trs' ? 'block' : 'none' }}
        >
          <Transcription
            transcript={memory.transcript_segments}
            externalData={memory.external_data}
            people={memory.people}
            participants={memory.structured.participants}
          />
        </div>
        <div
          className="sn-tabpanel"
          style={{ display: currentTab === 'chat' ? 'block' : 'none' }}
        >
          <Chat
            conversationId={memory.id}
            transcript={memory.transcript_segments}
            onClearChatRef={handleClearChatRef}
            onMessagesChange={setHasMessages}
            onChatEvent={(event) =>
              document.dispatchEvent(
                new CustomEvent('omi:shared-chat-action', { detail: event }),
              )
            }
          />
        </div>
      </div>
    </Fragment>
  );
}
