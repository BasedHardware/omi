'use client';

import { Page, List, Message } from 'iconoir-react';

interface TabsProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  onNewChat?: () => void;
  showNewChat?: boolean;
}

export default function Tabs({ currentTab, setCurrentTab, onNewChat, showNewChat }: TabsProps) {
  return (
    <div className="mt-4 flex items-center gap-3 border-b border-zinc-800 md:mt-6">
      <div className="flex gap-1">
        <button
          onClick={() => setCurrentTab('sum')}
          className={`group relative flex items-center gap-2 px-4 py-3 text-sm transition md:text-base ${
            currentTab === 'sum' ? 'text-white' : 'text-zinc-400 hover:text-zinc-300'
          }`}
        >
          <List className="h-4 w-4" />
          Summary
          {currentTab === 'sum' && (
            <span className="absolute inset-x-0 -bottom-px h-0.5 bg-gradient-to-r from-blue-500 to-purple-500" />
          )}
        </button>
        <button
          onClick={() => setCurrentTab('trs')}
          className={`group relative flex items-center gap-2 px-4 py-3 text-sm transition md:text-base ${
            currentTab === 'trs' ? 'text-white' : 'text-zinc-400 hover:text-zinc-300'
          }`}
        >
          <Page className="h-4 w-4" />
          Transcript
          {currentTab === 'trs' && (
            <span className="absolute inset-x-0 -bottom-px h-0.5 bg-gradient-to-r from-blue-500 to-purple-500" />
          )}
        </button>
        <button
          onClick={() => setCurrentTab('chat')}
          className={`group relative flex items-center gap-2 px-4 py-3 text-sm transition md:text-base ${
            currentTab === 'chat' ? 'text-white' : 'text-zinc-400 hover:text-zinc-300'
          }`}
        >
          <Message className="h-4 w-4" />
          Chat
          {currentTab === 'chat' && (
            <span className="absolute inset-x-0 -bottom-px h-0.5 bg-gradient-to-r from-blue-500 to-purple-500" />
          )}
        </button>
      </div>
      {showNewChat && currentTab === 'chat' && onNewChat && (
        <button
          onClick={onNewChat}
          className="inline-flex items-center rounded-full bg-zinc-800/50 px-3 py-1 text-xs text-zinc-400 ring-1 ring-inset ring-zinc-800 transition-all hover:bg-zinc-800 hover:text-zinc-300 md:text-sm"
        >
          New Chat
        </button>
      )}
    </div>
  );
}
