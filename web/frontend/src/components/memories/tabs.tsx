'use client';

import { Page, List, Message } from 'iconoir-react';

interface TabsProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  onNewChat?: () => void;
  showNewChat?: boolean;
}

export default function Tabs({
  currentTab,
  setCurrentTab,
  onNewChat,
  showNewChat,
}: TabsProps) {
  return (
    <div className="sn-tabs">
      <div className="sn-tabs-list">
        <button
          onClick={() => setCurrentTab('sum')}
          className={`sn-tab${currentTab === 'sum' ? ' sn-tab-active' : ''}`}
        >
          <List className="h-4 w-4" />
          Summary
        </button>
        <button
          onClick={() => setCurrentTab('trs')}
          className={`sn-tab${currentTab === 'trs' ? ' sn-tab-active' : ''}`}
        >
          <Page className="h-4 w-4" />
          Transcript
        </button>
        <button
          onClick={() => setCurrentTab('chat')}
          className={`sn-tab${currentTab === 'chat' ? ' sn-tab-active' : ''}`}
        >
          <Message className="h-4 w-4" />
          Chat
        </button>
      </div>
      {showNewChat && currentTab === 'chat' && onNewChat && (
        <button onClick={onNewChat} className="sn-newchat">
          New Chat
        </button>
      )}
    </div>
  );
}
