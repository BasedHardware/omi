// Hermetic evidence fixture: real tabs, gallery, tiles and admission helper.
// Network API and analytics imports are replaced by render-processingtoday.ts.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ConversationGallery } from '@/components/conversations/ConversationGallery';
import {
  FolderTabs,
  FOLDER_ACTIVITY,
  FOLDER_ALL,
} from '@/components/conversations/FolderTabs';
import { conversationsForSurface } from '@/lib/conversationHome';
import { buildTimelineDayGroups } from '@/lib/conversationTimeline';
import type { Conversation } from '@/types/conversation';

const failed = {
  id: 'unfinished-planning',
  created_at: '2026-11-10T13:00:00Z',
  started_at: '2026-11-10T13:00:00Z',
  finished_at: '2026-11-10T13:10:00Z',
  status: 'processing',
  home_step: 'failed',
  starred: false,
  transcript_segments: [],
  structured: {
    title: 'Unfinished planning',
    overview: '',
    emoji: '📝',
    action_items: [],
    events: [],
    category: 'work',
  },
} as unknown as Conversation;
const ready = {
  ...failed,
  id: 'coffee',
  home_step: 'done',
  status: 'completed',
  structured: {
    ...failed.structured,
    title: 'Coffee with Alex',
    overview: 'Plans for the week and a quick catch-up.',
  },
} as Conversation;

function Evidence() {
  const [rows, setRows] = useState([failed, ready]);
  const [tab, setTab] = useState(FOLDER_ALL);
  const confirmed = new URLSearchParams(location.search).get('rollback') !== '1';
  const visible = conversationsForSurface(rows, tab === FOLDER_ACTIVITY, confirmed);
  const groups = buildTimelineDayGroups({
    conversations: visible,
    recaps: [],
    now: new Date('2026-11-10T16:00:00Z'),
  });
  return (
    <main style={{ maxWidth: 1120, margin: '40px auto', height: 700 }}>
      <h1 style={{ fontSize: 28, marginBottom: 24 }}>Conversations</h1>
      <div style={{ marginBottom: 24 }}>
        <FolderTabs
          folders={[]}
          selectedFolderId={tab}
          showActivity={confirmed}
          onSelectFolder={setTab}
          onCreateFolder={() => {}}
        />
      </div>
      <ConversationGallery
        groups={groups}
        selectedId={null}
        onConversationClick={() => {}}
        onRecapClick={() => {}}
        onConversationUpdate={(updated) =>
          setRows((old) => old.map((row) => (row.id === updated.id ? updated : row)))
        }
      />
    </main>
  );
}
createRoot(document.getElementById('root')!).render(<Evidence />);
