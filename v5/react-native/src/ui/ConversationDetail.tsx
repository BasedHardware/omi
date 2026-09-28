import React, {useRef} from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  Text,
  TextInput,
  View,
} from 'react-native';
import type {ConversationProjection} from '../desktopReadClient';
import {RecordingTranscript} from './RecordingTranscript';
import {ChatConversationHistory} from './ChatConversationHistory';
import {MAIN_CHAT_CONVERSATION_ID} from '../chatConversationHistory';
import {useDesktopTheme} from '../desktop/DesktopTheme';
import {styles} from './styles';
import {FocusPressable} from './Pressable';
import {useLegacyConversationDetail} from '../useLegacyConversationDetail';
import {omiBackend} from '../omiNative';
import {
  conversationShareUrl,
  deleteConversation,
  listFolders,
  moveConversationToFolder,
  reprocessConversation,
  setConversationTitle,
  setConversationVisibility,
  type LegacyFolder,
} from '../legacyOmiWrites';

export function formatConversationDate(value: string | null): string {
  if (value === null) {
    return 'Time unavailable';
  }
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    month: 'short',
  }).format(new Date(value));
}

export function formatConversationDuration(
  startedAt: string | null,
  finishedAt: string | null,
): string {
  if (startedAt === null || finishedAt === null) {
    return 'Duration unavailable';
  }
  const duration = Date.parse(finishedAt) - Date.parse(startedAt);
  if (!Number.isFinite(duration) || duration < 0) {
    return 'Duration unavailable';
  }
  const minutes = Math.round(duration / 60_000);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes === 0
    ? `${hours} hr`
    : `${hours} hr ${remainingMinutes} min`;
}

export function ConversationDetail({
  conversation,
  desktop = false,
  apiContract,
  onRefresh,
  onDeleted,
}: {
  conversation: ConversationProjection;
  desktop?: boolean;
  apiContract?: 'omi';
  onRefresh?: () => void;
  onDeleted?: () => void;
}) {
  const {tokens: desktopTokens} = useDesktopTheme();
  if (apiContract === 'omi') {
    return (
      <LegacyConversationBody
        key={conversation.id}
        conversation={conversation}
        desktop={desktop}
        onRefresh={onRefresh}
        onDeleted={onDeleted}
      />
    );
  }
  const ink = desktop ? {color: desktopTokens.color.ink} : undefined;
  return (
    <>
      <Text style={[styles.conversationDetailTitle, ink]}>
        {conversation.title}
      </Text>
      <Text style={[styles.conversationDetailSummary, ink]}>
        {conversation.summary}
      </Text>
      <View style={styles.conversationDetailFields}>
        {conversation.capturedAtMs !== undefined && (
          <Text style={[styles.conversationDetailField, ink]}>
            Captured (device time) ·{' '}
            {new Date(conversation.capturedAtMs).toLocaleString()}
          </Text>
        )}
        <Text style={[styles.conversationDetailField, ink]}>
          Started · {formatConversationDate(conversation.startedAt)}
        </Text>
        <Text style={[styles.conversationDetailField, ink]}>
          Finished · {formatConversationDate(conversation.finishedAt)}
        </Text>
        <Text style={[styles.conversationDetailField, ink]}>
          Duration ·{' '}
          {formatConversationDuration(
            conversation.startedAt,
            conversation.finishedAt,
          )}
        </Text>
        <Text style={[styles.conversationDetailField, ink]}>
          Status · {conversation.status}
        </Text>
        {conversation.locked && (
          <Text style={[styles.conversationDetailField, ink]}>Locked</Text>
        )}
        {conversation.discarded && (
          <Text style={[styles.conversationDetailField, ink]}>Discarded</Text>
        )}
      </View>
      {conversation.source === 'omi' &&
        conversation.id.startsWith('recording:') &&
        conversation.id.length > 'recording:'.length && (
          <RecordingTranscript
            desktop={desktop}
            key={conversation.id}
            sessionId={conversation.id.slice('recording:'.length)}
            revision={conversation.updatedAt ?? undefined}
          />
        )}
      {conversation.source === 'chat' &&
        conversation.id === MAIN_CHAT_CONVERSATION_ID && (
          <ChatConversationHistory key={conversation.id} desktop={desktop} />
        )}
      {conversation.source === 'chat' &&
        conversation.id !== MAIN_CHAT_CONVERSATION_ID && (
          <Text style={[styles.conversationDetailSummary, ink]}>
            Chat history for this conversation is not available here.
          </Text>
        )}
    </>
  );
}

function LegacyConversationBody({
  conversation,
  desktop,
  onRefresh,
  onDeleted,
}: {
  conversation: ConversationProjection;
  desktop: boolean;
  onRefresh?: () => void;
  onDeleted?: () => void;
}) {
  const {tokens: desktopTokens} = useDesktopTheme();
  const {result, reload} = useLegacyConversationDetail(
    conversation.id,
    conversation.updatedAt,
  );
  const [title, setTitle] = React.useState(conversation.title);
  const [editing, setEditing] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [folders, setFolders] = React.useState<LegacyFolder[]>([]);
  const [showFolders, setShowFolders] = React.useState(false);
  const writePending = useRef(false);
  const ink = desktop ? {color: desktopTokens.color.ink} : undefined;
  React.useEffect(() => {
    setTitle(conversation.title);
  }, [conversation.id, conversation.title]);
  React.useEffect(() => {
    if (desktop && Platform.OS === 'macos') {
      void listFolders(omiBackend as NonNullable<typeof omiBackend>).then(
        result => {
          if (result.ok) setFolders(result.value);
        },
      );
    }
  }, [conversation.id, desktop]);
  const finishWrite = async (
    action: string,
    operation: () => Promise<{ok: boolean; failure?: {detail: string}}>,
  ) => {
    if (writePending.current || busy !== null) return false;
    writePending.current = true;
    setBusy(action);
    setNotice(null);
    try {
      const result = await operation();
      if (!result.ok) {
        setNotice(
          result.failure?.detail ?? 'The change could not be confirmed.',
        );
        return false;
      }
      if (action === 'delete') {
        onRefresh?.();
        onDeleted?.();
        return true;
      }
      await reload();
      onRefresh?.();
      return true;
    } catch {
      setNotice('The change could not be confirmed. Refresh and try again.');
      return false;
    } finally {
      writePending.current = false;
      setBusy(null);
    }
  };
  if (result.status === 'idle' || result.status === 'loading') {
    return (
      <View>
        <ActivityIndicator
          color={desktop ? desktopTokens.color.inkMuted : '#aaaaaa'}
        />
        <Text style={[styles.conversationDetailSummary, ink]}>
          Loading conversation…
        </Text>
      </View>
    );
  }
  if (result.status === 'error') {
    return (
      <View>
        <Text
          accessibilityRole="alert"
          style={[styles.conversationDetailSummary, ink]}>
          {result.error}
        </Text>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Retry conversation details"
          onPress={reload}
          style={styles.conversationTranscriptAction}>
          <Text style={[styles.conversationDetailField, ink]}>Try again</Text>
        </FocusPressable>
      </View>
    );
  }
  const detail = result.value;
  return (
    <>
      <TextInput
        accessibilityLabel="Conversation title"
        onBlur={() => {
          setEditing(false);
          if (title.trim() && title.trim() !== detail.title)
            void finishWrite('title', () =>
              setConversationTitle(omiBackend!, conversation.id, title.trim()),
            );
        }}
        onChangeText={setTitle}
        onFocus={() => setEditing(true)}
        onSubmitEditing={() => {
          setEditing(false);
          if (title.trim() && title.trim() !== detail.title)
            void finishWrite('title', () =>
              setConversationTitle(omiBackend!, conversation.id, title.trim()),
            );
        }}
        returnKeyType="done"
        style={[styles.conversationDetailTitle, ink]}
        value={editing ? title : detail.title}
      />
      <View style={styles.conversationDetailFields}>
        <WriteAction
          label={busy === 'reprocess' ? 'Reprocessing…' : 'Reprocess'}
          disabled={busy !== null}
          onPress={() =>
            void finishWrite('reprocess', async () => {
              return reprocessConversation(omiBackend!, conversation.id);
            })
          }
        />
        <WriteAction
          label={busy === 'share' ? 'Sharing…' : 'Share'}
          disabled={busy !== null}
          onPress={() =>
            void (async () => {
              if (writePending.current) return;
              writePending.current = true;
              setBusy('share');
              setNotice(null);
              try {
                const shared = await setConversationVisibility(
                  omiBackend!,
                  conversation.id,
                  'shared',
                );
                if (!shared.ok) {
                  setNotice(shared.failure.detail);
                  return;
                }
                await reload();
                onRefresh?.();
                let url: string | null = null;
                try {
                  url = await conversationShareUrl(
                    omiBackend!,
                    conversation.id,
                  );
                  if (!omiBackend?.copyToClipboard)
                    throw new Error('Clipboard is unavailable');
                  await omiBackend.copyToClipboard(url);
                  setNotice('Copied');
                } catch {
                  setNotice(
                    url === null
                      ? 'Sharing enabled'
                      : `Sharing enabled. Copy this link: ${url}`,
                  );
                }
              } finally {
                writePending.current = false;
                setBusy(null);
              }
            })()
          }
        />
        <WriteAction
          label="Delete"
          disabled={busy !== null}
          onPress={() =>
            Alert.alert(
              'Delete conversation?',
              'This permanently deletes the conversation and its derived memories and action items.',
              [
                {text: 'Cancel', style: 'cancel'},
                {
                  text: 'Delete',
                  style: 'destructive',
                  onPress: () =>
                    void finishWrite('delete', async () => {
                      return deleteConversation(omiBackend!, conversation.id);
                    }),
                },
              ],
            )
          }
        />
        {desktop && Platform.OS === 'macos' && (
          <>
            <WriteAction
              label="Move to folder"
              disabled={busy !== null}
              onPress={() => setShowFolders(value => !value)}
            />
            {showFolders && (
              <>
                <WriteAction
                  label="No folder"
                  disabled={busy !== null}
                  onPress={() =>
                    void finishWrite('folder', () =>
                      moveConversationToFolder(
                        omiBackend!,
                        conversation.id,
                        null,
                      ),
                    )
                  }
                />
                {folders.map(folder => (
                  <WriteAction
                    key={folder.id}
                    label={folder.name}
                    disabled={busy !== null}
                    onPress={() =>
                      void finishWrite('folder', () =>
                        moveConversationToFolder(
                          omiBackend!,
                          conversation.id,
                          folder.id,
                        ),
                      )
                    }
                  />
                ))}
              </>
            )}
          </>
        )}
        {notice && (
          <Text
            accessibilityRole="alert"
            style={[styles.conversationDetailField, ink]}>
            {notice}
          </Text>
        )}
      </View>
      <Text selectable style={[styles.conversationDetailSummary, ink]}>
        {detail.summary}
      </Text>
      {detail.sections.map((section, index) => (
        <View key={index} style={styles.conversationDetailFields}>
          <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
            {section.heading}
          </Text>
          <Text selectable style={[styles.conversationTranscriptText, ink]}>
            {section.bodyMarkdown}
          </Text>
        </View>
      ))}
      <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
        Transcript
      </Text>
      {detail.transcript.status === 'unavailable' ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          {detail.locked
            ? 'This conversation is locked. Transcript unavailable.'
            : 'Transcript unavailable for this conversation.'}
        </Text>
      ) : detail.transcript.segments.length === 0 ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          The transcript is empty.
        </Text>
      ) : (
        detail.transcript.segments.map((segment, index) => (
          <Text
            key={index}
            selectable
            style={[styles.conversationTranscriptText, ink]}>
            {segment.isUser
              ? 'You'
              : segment.speaker?.replace(
                  /^SPEAKER_(\d+)$/,
                  (_, number: string) => `Speaker ${Number(number) + 1}`,
                ) || 'Speaker'}{' '}
            · {segment.text}
          </Text>
        ))
      )}
    </>
  );
}

function WriteAction({
  label,
  disabled,
  onPress,
}: {
  label: string;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <FocusPressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={styles.conversationTranscriptAction}>
      <Text style={styles.conversationDetailField}>{label}</Text>
    </FocusPressable>
  );
}
