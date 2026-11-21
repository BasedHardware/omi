import React, { useEffect, useMemo, useState } from 'react';
import {
  View, Text, ScrollView, TextInput, TouchableOpacity, StyleSheet, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMemoriesStore } from '@/state/memoriesStore';
import { useConversationsStore } from '@/state/conversationsStore';
import { useAuthStore } from '@/state/authStore';
import { createActionItem } from '@/api/omiApi';
import {
  routeWithProvider,
  ROUTE_PROTOTYPES,
  OUT_OF_DOMAIN_PROTOTYPES,
  type Route,
} from '@/services/localBrainRouter';
import { createNativeRouter, isLocalBrainAvailable } from '../../modules/local-brain';
import { answerLocally } from '@/services/localAssistant';
import { LocalBrainBar, type RouteTrace } from '@/components/LocalBrainBar';
import { usePhoneVoiceAgentStore } from '@/services/phoneVoiceAgent';
import { getGraphStats, loadBrainState, processUnprocessedConversations } from '@/services/localBrain';
import { Card, EmptyState, Pill, SectionHeader } from '@/ui/components';
import { OmiColors, OmiRadius, OmiSpacing, OmiType } from '@/ui/tokens';
import { DEV_LOCAL_BRAIN, GUEST_MODE } from '@/devFlags';
import type { Conversation, Memory } from '@/api/omiApi';

function dayLabel(iso?: string): string {
  if (!iso) return 'Unknown';
  const d = new Date(iso);
  const today = new Date();
  const y = new Date(today); y.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === y.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function groupByDay(conversations: Conversation[]): { label: string; items: Conversation[] }[] {
  const map = new Map<string, Conversation[]>();
  for (const c of conversations) {
    const label = dayLabel(c.created_at);
    if (!map.has(label)) map.set(label, []);
    map.get(label)!.push(c);
  }
  return Array.from(map.entries()).map(([label, items]) => ({ label, items }));
}

function buildMindMap(memories: Memory[]): { tag: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const m of memories) {
    for (const t of m.tags ?? []) {
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 12);
}

export default function HomeScreen() {
  const memories = useMemoriesStore((s) => s.items);
  const conversations = useConversationsStore((s) => s.items);
  const loadMemories = useMemoriesStore((s) => s.load);
  const loadConversations = useConversationsStore((s) => s.load);
  const router = useRouter();
  const [query, setQuery] = useState('');
  const uid = useAuthStore((s) => s.uid);

  // Routing is the embedder when the native module is present, and the existing
  // regexes otherwise. Built once and reused: configure() crosses the bridge on
  // the first call and caches the promise on the provider.
  const brainRouter = useMemo(
    () =>
      isLocalBrainAvailable
        ? createNativeRouter(ROUTE_PROTOTYPES, OUT_OF_DOMAIN_PROTOTYPES)
        : null,
    []
  );

  const [trace, setTrace] = useState<RouteTrace | null>(null);
  const [answer, setAnswer] = useState<{ text: string; kind: string } | null>(null);
  const [answering, setAnswering] = useState(false);
  const [brainStats, setBrainStats] = useState<{ nodeCount: number; edgeCount: number; byType: Record<string, number> } | null>(null);
  const [brainTopics, setBrainTopics] = useState<{ tag: string; count: number }[]>([]);

  const voiceStatus = usePhoneVoiceAgentStore((s) => s.status);
  const voiceHeard = usePhoneVoiceAgentStore((s) => s.heard);
  const voiceReply = usePhoneVoiceAgentStore((s) => s.reply);
  const voiceError = usePhoneVoiceAgentStore((s) => s.error);
  const toggleVoice = usePhoneVoiceAgentStore((s) => s.toggle);

  // On-device local agent: a task/reminder command is handled without the cloud;
  // anything else falls through to "Ask Omi" chat.
  const submit = async (): Promise<void> => {
    const text = query.trim();
    if (!text) return;
    const outcome = await routeWithProvider(text, brainRouter);
    setTrace({
      source: outcome.source,
      route:
        outcome.decision.kind === 'chat'
          ? 'chat'
          : (outcome.decision.kind as Route),
      margin: 'margin' in outcome ? outcome.margin : 0,
      reason: outcome.source === 'heuristic' ? outcome.reason : undefined,
    });
    const action = outcome.decision;
    if (action.kind === 'chat') {
      // Answered from on-device storage, not generated. See localAssistant: the
      // brain is an embedder, so every answer is either something recorded or an
      // explicit refusal. Shown in the transcript rather than an Alert, because
      // an answer belongs in the conversation, not a dialog the user dismisses.
      setAnswering(true);
      try {
        const reply = await answerLocally(text);
        setAnswer({ text: reply.text, kind: reply.kind });
      } finally {
        setAnswering(false);
      }
      return;
    }
    if (!uid && !GUEST_MODE) {
      Alert.alert('Sign in required', 'Sign in so tasks sync to your account.');
      return;
    }
    let due_at: string | null = null;
    if (action.kind === 'create_reminder' && action.minutesFromNow) {
      due_at = new Date(Date.now() + action.minutesFromNow * 60_000).toISOString();
    }
    try {
      await createActionItem(action.title, { due_at });
      setQuery('');
      Alert.alert(
        action.kind === 'create_reminder' ? 'Reminder set' : 'Task added',
        action.title
      );
    } catch {
      Alert.alert('Could not save', 'Check your connection and try again.');
    }
  };

  useEffect(() => {
    loadMemories();
    loadConversations();
    void (async () => {
      try {
        await processUnprocessedConversations(20);
      } catch {}
      try {
        const state = await loadBrainState();
        setBrainStats(getGraphStats(state.graph));
        const topicCounts = new Map<string, number>();
        for (const n of Object.values(state.graph.nodes)) {
          if (n.status === 'forgotten') continue;
          if (n.type === 'topic') topicCounts.set(n.label, (topicCounts.get(n.label) ?? 0) + 1);
        }
        const topics = Array.from(topicCounts.entries())
          .map(([tag, count]) => ({ tag, count }))
          .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
          .slice(0, 12);
        setBrainTopics(topics);
      } catch {}
    })();
  }, [loadMemories, loadConversations]);

  const recaps = useMemo(() => groupByDay(conversations).slice(0, 5), [conversations]);
  const mindMap = useMemo(() => {
    const remote = buildMindMap(memories);
    if (brainTopics.length === 0) return remote;
    const merged = new Map<string, number>();
    for (const m of remote) merged.set(m.tag, (merged.get(m.tag) ?? 0) + m.count);
    for (const t of brainTopics) merged.set(t.tag, (merged.get(t.tag) ?? 0) + t.count);
    return Array.from(merged.entries())
      .map(([tag, count]) => ({ tag, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 14);
  }, [memories, brainTopics]);

  const voiceTone: 'neutral' | 'accent' | 'success' | 'warning' | 'danger' =
    voiceStatus === 'listening'
      ? 'danger'
      : voiceStatus === 'thinking' || voiceStatus === 'speaking'
        ? 'accent'
        : voiceError
          ? 'danger'
          : 'neutral';

  const voiceLabel =
    voiceStatus === 'listening'
      ? 'Listening'
      : voiceStatus === 'thinking'
        ? 'Thinking'
        : voiceStatus === 'speaking'
          ? 'Speaking'
          : voiceError
            ? 'Needs attention'
            : voiceReply
              ? 'Voice reply'
              : 'Voice ready';

  const showVoiceCard = voiceStatus !== 'idle' || !!voiceReply || !!voiceError;
  const showTextAnswer = !!answer && !showVoiceCard;

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>LOCAL BRAIN</Text>
            <Text style={styles.title}>Omi</Text>
            <Text style={styles.subtitle}>Conversations, memory, and a phone-first voice agent.</Text>
          </View>
          <View style={styles.headerActions}>
            <TouchableOpacity
              style={styles.secondaryPill}
              onPress={() => router.push('/omi-device')}
              activeOpacity={0.85}
            >
              <Text style={styles.secondaryPillText}>Connect</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.primaryPill}
              onPress={() => router.push('/capture')}
              activeOpacity={0.85}
            >
              <Text style={styles.primaryPillDot}>●</Text>
              <Text style={styles.primaryPillText}>Record</Text>
            </TouchableOpacity>
          </View>
        </View>

        <Card style={styles.heroCard}>
          <View style={styles.heroTop}>
            <View style={styles.heroCopy}>
              <Text style={styles.heroTitle}>Ask or talk to Omi</Text>
              <Text style={styles.heroBody}>
                Type a question, add a task, or use your voice. Voice replies are grounded in what’s on this device.
              </Text>
            </View>
            <Pill label={voiceLabel} tone={voiceTone} />
          </View>
          <View style={styles.inputBox}>
            <TextInput
              style={styles.input}
              placeholder="Ask anything, or say “remind me to…”"
              placeholderTextColor={OmiColors.textTertiary}
              value={query}
              onChangeText={setQuery}
              onSubmitEditing={() => void submit()}
              returnKeyType="send"
            />
            <TouchableOpacity
              style={[styles.micBtn, voiceStatus === 'listening' && styles.micBtnActive]}
              activeOpacity={0.85}
              onPress={toggleVoice}
              accessibilityRole="button"
              accessibilityLabel={
                voiceStatus === 'listening' ? 'Stop listening and send' : 'Start voice agent'
              }
            >
              <Text style={styles.micIcon}>{voiceStatus === 'listening' ? '■' : '🎙'}</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.inputHint}>
            {voiceStatus === 'listening'
              ? 'Listening on your phone mic. Tap stop when you’re done speaking.'
              : 'Tip: try “what did we talk about today?” or “add a task: buy milk”.'}
          </Text>
        </Card>

        {showVoiceCard && (
          <Card style={styles.statusCard}>
            <View style={styles.statusRow}>
              <Pill label={voiceLabel} tone={voiceTone} />
              {voiceStatus === 'listening' ? (
                <Text style={styles.statusMeta}>Tap mic to send</Text>
              ) : null}
            </View>
            {voiceHeard ? <Text style={styles.heardText}>You said: “{voiceHeard}”</Text> : null}
            <Text style={styles.answerText}>{voiceError ?? voiceReply ?? '…'}</Text>
          </Card>
        )}

        {showTextAnswer && (
          <Card style={styles.statusCard}>
            <View style={styles.statusRow}>
              <Pill
                label={
                  answering
                    ? 'Thinking'
                    : answer?.kind === 'quote'
                      ? 'From recordings'
                      : answer?.kind === 'summary'
                        ? 'Closest match'
                        : answer?.kind === 'unsupported'
                          ? 'Needs server'
                          : 'No match'
                }
                tone={answering ? 'accent' : answer?.kind === 'empty' ? 'neutral' : 'success'}
              />
            </View>
            <Text style={styles.answerText}>{answer?.text}</Text>
          </Card>
        )}

        <SectionHeader title="Conversations" action={conversations.length > 4 ? 'See all' : undefined} onPressAction={() => router.push('/(tabs)/conversations')} />
        {conversations.length === 0 ? (
          <EmptyState text="No conversations yet. Record or capture to start building your local brain." />
        ) : (
          conversations.slice(0, 4).map((c) => (
            <Card
              key={c.id}
              style={styles.rowCard}
              onPress={() => router.push({ pathname: '/conversation/[id]', params: { id: c.id } })}
            >
              <View style={styles.rowMain}>
                <Text style={styles.rowTitle} numberOfLines={1}>{c.title ?? c.id}</Text>
                <Text style={styles.rowSub}>{dayLabel(c.created_at)}</Text>
              </View>
              <Text style={styles.rowChevron}>›</Text>
            </Card>
          ))
        )}

        <SectionHeader title="Daily Recaps" />
        {recaps.length === 0 ? (
          <EmptyState text="Recaps will appear as your conversations build up." />
        ) : (
          recaps.map((r) => (
            <Card key={r.label} style={styles.recapCard}>
              <View style={styles.recapHeader}>
                <Text style={styles.recapDay}>{r.label}</Text>
                <Text style={styles.recapCount}>{r.items.length}</Text>
              </View>
              {r.items.slice(0, 3).map((c) => (
                <Text key={c.id} style={styles.recapItem} numberOfLines={1}>• {c.title ?? c.id}</Text>
              ))}
            </Card>
          ))
        )}

        <SectionHeader title="Mind Map" />
        {brainStats ? (
          <Text style={styles.graphMeta}>
            Local knowledge graph: {brainStats.nodeCount} nodes · {brainStats.edgeCount} links
          </Text>
        ) : null}
        {mindMap.length === 0 ? (
          <EmptyState text="Topics and tags will show up here from your memories and local brain." />
        ) : (
          <View style={styles.mindWrap}>
            {mindMap.map((m) => (
              <View key={m.tag} style={styles.mindNode}>
                <Text style={styles.mindTag}>{m.tag}</Text>
                <Text style={styles.mindCount}>{m.count}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Routing transparency: which layer decided, and how confident it was. */}
      <LocalBrainBar trace={trace} />

      {DEV_LOCAL_BRAIN && (
        <View style={styles.devRow}>
          <TouchableOpacity style={styles.devBtn} onPress={() => router.push('/dev-local-brain')}>
            <Text style={styles.devBtnText}>Local brain</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.devBtn} onPress={() => router.push('/dev-omi-device')}>
            <Text style={styles.devBtnText}>omi device</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: OmiColors.surface0 },
  scroll: { flex: 1 },
  scrollContent: {
    paddingHorizontal: OmiSpacing.lg,
    paddingTop: OmiSpacing.xxl + 8,
    paddingBottom: OmiSpacing.xxl,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: OmiSpacing.md,
    marginBottom: OmiSpacing.lg,
  },
  eyebrow: {
    ...OmiType.caption,
    color: OmiColors.textTertiary,
    letterSpacing: 1.2,
    fontWeight: '600',
    marginBottom: 4,
  },
  title: {
    ...OmiType.largeTitle,
    color: OmiColors.textPrimary,
    marginBottom: 4,
  },
  subtitle: {
    ...OmiType.subhead,
    color: OmiColors.textSecondary,
    maxWidth: 320,
  },
  headerActions: {
    flexDirection: 'row',
    gap: OmiSpacing.xs,
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
  },
  primaryPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: OmiColors.accent,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: OmiRadius.pill,
  },
  primaryPillDot: { color: OmiColors.danger, fontSize: 10 },
  primaryPillText: { ...OmiType.subhead, color: OmiColors.onAccent, fontWeight: '600' },
  secondaryPill: {
    backgroundColor: OmiColors.surface2,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: OmiRadius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: OmiColors.border,
  },
  secondaryPillText: { ...OmiType.subhead, color: OmiColors.textPrimary, fontWeight: '600' },
  heroCard: {
    padding: OmiSpacing.lg,
    backgroundColor: OmiColors.surface1,
    marginBottom: OmiSpacing.md,
  },
  heroTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: OmiSpacing.sm,
    marginBottom: OmiSpacing.md,
  },
  heroCopy: { flex: 1, gap: 4 },
  heroTitle: { ...OmiType.title3, color: OmiColors.textPrimary },
  heroBody: { ...OmiType.subhead, color: OmiColors.textSecondary },
  inputBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: OmiColors.surface2,
    borderRadius: OmiRadius.xl,
    paddingHorizontal: OmiSpacing.md,
    paddingVertical: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: OmiColors.border,
  },
  input: {
    flex: 1,
    ...OmiType.body,
    color: OmiColors.textPrimary,
    paddingVertical: 10,
    paddingRight: 8,
  },
  micBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: OmiColors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  micBtnActive: { backgroundColor: OmiColors.danger },
  micIcon: { fontSize: 16 },
  inputHint: {
    ...OmiType.footnote,
    color: OmiColors.textTertiary,
    marginTop: OmiSpacing.sm,
  },
  statusCard: {
    marginBottom: OmiSpacing.sm,
    backgroundColor: OmiColors.surface1,
    gap: OmiSpacing.xs,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  statusMeta: { ...OmiType.caption, color: OmiColors.textTertiary },
  heardText: { ...OmiType.footnote, color: OmiColors.textSecondary },
  answerText: { ...OmiType.body, color: OmiColors.textPrimary },
  rowCard: {
    marginBottom: OmiSpacing.xs,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: OmiSpacing.sm + 2,
  },
  rowMain: { flex: 1, paddingRight: OmiSpacing.sm },
  rowTitle: { ...OmiType.headline, color: OmiColors.textPrimary },
  rowSub: { ...OmiType.footnote, color: OmiColors.textTertiary, marginTop: 2 },
  rowChevron: { ...OmiType.title3, color: OmiColors.textDisabled },
  recapCard: { marginBottom: OmiSpacing.xs, gap: 4 },
  recapHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  recapDay: { ...OmiType.headline, color: OmiColors.textPrimary },
  recapCount: { ...OmiType.caption, color: OmiColors.textTertiary },
  recapItem: { ...OmiType.subhead, color: OmiColors.textSecondary },
  mindWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: OmiSpacing.xs },
  mindNode: {
    backgroundColor: OmiColors.surface2,
    borderRadius: OmiRadius.pill,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: OmiColors.border,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  mindTag: { ...OmiType.subhead, color: OmiColors.textPrimary, fontWeight: '600' },
  mindCount: { ...OmiType.caption, color: OmiColors.textTertiary },
  graphMeta: { ...OmiType.footnote, color: OmiColors.textSecondary, marginBottom: OmiSpacing.xs },
  devRow: {
    flexDirection: 'row',
    gap: OmiSpacing.xs,
    paddingHorizontal: OmiSpacing.lg,
    paddingBottom: OmiSpacing.sm,
    backgroundColor: OmiColors.surface0,
  },
  devBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: OmiRadius.md,
    backgroundColor: OmiColors.surface2,
    alignItems: 'center',
  },
  devBtnText: { ...OmiType.footnote, color: OmiColors.textSecondary, fontWeight: '600' },
});
