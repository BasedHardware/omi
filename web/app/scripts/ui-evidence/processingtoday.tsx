// Hermetic evidence fixture: real tabs, gallery, tiles and admission helper.
// Network API and analytics imports are replaced by render-processingtoday.ts.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ConversationGallery } from '@/components/conversations/ConversationGallery';
import { AttentionItemsSection } from '@/components/conversations/AttentionItemsSection';
import { useAttentionItems } from '@/hooks/useAttentionItems';
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
  const caseNumber = new URLSearchParams(location.search).get('notes');
  const caseIndex = Number(caseNumber) - 10;
  const kept = {
    ...failed,
    id: 'kept-outputs',
    home_step: caseIndex === 0 ? 'failed' : 'noise',
    status: 'completed',
    structured: {
      ...failed.structured,
      title: ['Planning follow-up', 'Actions captured', 'Meeting scheduled'][caseIndex],
      action_items:
        caseIndex !== 2
          ? [{ description: 'Send the design follow-up', completed: false }]
          : [],
      events:
        caseIndex !== 1
          ? [
              {
                title: 'Planning meeting',
                start: '2026-11-11T10:00:00Z',
                duration: 30,
                created: true,
              },
            ]
          : [],
    },
  } as Conversation;
  const [rows, setRows] = useState([caseNumber ? kept : failed, ready]);
  (window as unknown as { savedOutputs: string }).savedOutputs = JSON.stringify(
    rows[0].structured,
  );

  const [tab, setTab] = useState(FOLDER_ALL);
  const confirmed = new URLSearchParams(location.search).get('rollback') !== '1';
  const attention = useAttentionItems(confirmed, 'fixture');
  const visible = conversationsForSurface(
    rows,
    tab === FOLDER_ACTIVITY,
    confirmed,
  ).filter((row) => tab !== FOLDER_ACTIVITY || !attention.conversationIds.has(row.id));
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
      {confirmed && tab === FOLDER_ACTIVITY && (
        <AttentionItemsSection
          {...attention}
          onRetry={attention.retry}
          onOpen={() => {}}
        />
      )}
      <ConversationGallery
        showFailedStatus={confirmed && tab === FOLDER_ACTIVITY}
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
