'use client';

import { Page, List } from 'iconoir-react';

interface TabsProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
}

export default function Tabs({ currentTab, setCurrentTab }: TabsProps) {
  return (
    <div className="mt-8 flex gap-1 border-b border-zinc-800 px-6 md:mt-10 md:px-12">
      <button
        onClick={() => setCurrentTab('trs')}
        className={`group relative flex items-center gap-2 px-4 py-3 text-sm transition md:text-base ${
          currentTab === 'trs'
            ? 'text-white'
            : 'text-zinc-400 hover:text-zinc-300'
        }`}
      >
        <Page className="h-4 w-4" />
        Transcript
        {currentTab === 'trs' && (
          <span className="absolute inset-x-0 -bottom-px h-0.5 bg-gradient-to-r from-blue-500 to-purple-500" />
        )}
      </button>
      <button
        onClick={() => setCurrentTab('sum')}
        className={`group relative flex items-center gap-2 px-4 py-3 text-sm transition md:text-base ${
          currentTab === 'sum'
            ? 'text-white'
            : 'text-zinc-400 hover:text-zinc-300'
        }`}
      >
        <List className="h-4 w-4" />
        Summary
        {currentTab === 'sum' && (
          <span className="absolute inset-x-0 -bottom-px h-0.5 bg-gradient-to-r from-blue-500 to-purple-500" />
        )}
      </button>
    </div>
  );
}
