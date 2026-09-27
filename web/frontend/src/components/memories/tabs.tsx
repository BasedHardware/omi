'use client';

interface TabsProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  onNewChat?: () => void;
  showNewChat?: boolean;
}

const TABS = [
  { id: 'sum', label: 'Notes' },
  { id: 'trs', label: 'Transcript' },
  { id: 'chat', label: 'Ask Omi' },
];

export default function Tabs({
  currentTab,
  setCurrentTab,
  onNewChat,
  showNewChat,
}: TabsProps) {
  return (
    <div className="sn-tabs">
      <div className="sn-tabs-list" role="tablist" aria-label="Note views">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={currentTab === tab.id}
            onClick={() => setCurrentTab(tab.id)}
            className={`sn-tab${currentTab === tab.id ? ' sn-tab-active' : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {showNewChat && currentTab === 'chat' && onNewChat && (
        <button type="button" onClick={onNewChat} className="sn-newchat">
          New chat
        </button>
      )}
    </div>
  );
}
