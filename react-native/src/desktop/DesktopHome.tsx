import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  NativeModules,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  desktopProjectionUnavailableCopy,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
} from '../desktopReadClient';
import {matchesSearchQuery} from '../searchText';
import type {ReadsPhase} from '../app/useDesktopReads';
import {omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';
import {ScrollFade} from './ScrollFade';
import {ReadStatus} from '../ui/ReadStatus';
import {ShippingListInsert} from './ShippingStage';
import {MaterialIcon} from '../ui/MaterialIcon';

import {EXPLORE_CHECKLIST, type ExploreCheck} from './exploreChecklist';
import {
  EmptyCopy,
  PageHeading,
  ReadRow,
  SectionTitle,
  TaskRow,
} from './DesktopRows';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';

type Props = {
  draft: string;
  onRefresh: () => void;
  exploreDone?: Set<ExploreCheck> | null;
  onExploreGuide?: (check: ExploreCheck) => void;
  onOpenTasks?: () => void;
  onOpenConversations?: () => void;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
};

type GlanceFrame = {
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
};

const GLANCE_FRAME_FRESH_MS = 5 * 60 * 1000;
const GLANCE_POLL_MS = 15000;
const GLANCE_REFRESH_MS = 5 * 60 * 1000;

type GlanceLine = {title: string; copy: string};

/**
 * Asks the v5 worker for an AI-composed glance line (weather + live Mac
 * context). Any failure — old backend, offline, malformed response — simply
 * leaves the local line in place, so the glance always renders something.
 */
function useRemoteGlanceLine(input: {
  frame: GlanceFrame | null;
  counts: {conversations: number; memories: number; tasks: number};
}): GlanceLine | null {
  const [line, setLine] = useState<GlanceLine | null>(null);
  const fetchedAtRef = useRef(0);
  const contextKey = `${input.frame?.appName ?? ''}|${
    input.counts.conversations
  }|${input.counts.memories}|${input.counts.tasks}`;
  useEffect(() => {
    let cancelled = false;
    const fetchLine = async () => {
      const backend = omiBackend;
      if (backend === undefined || backend === null) {
        return;
      }
      if ((await backend.getApiContract?.()) !== 'canonical') {
        return;
      }
      const response = await backend.request({
        id: 'desktop-glance',
        method: 'POST',
        expectedApiContract: 'canonical',
        path: '/v1/desktop/glance',
        body: JSON.stringify({
          frontApp: input.frame?.appName.slice(0, 120) ?? '',
          windowTitle: input.frame?.windowTitle.slice(0, 120) ?? '',
          counts: input.counts,
          localTimeIso: new Date().toISOString(),
        }),
      });
      if (cancelled || response.status !== 200 || response.body == null) {
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(response.body);
      } catch {
        return;
      }
      if (
        parsed !== null &&
        typeof parsed === 'object' &&
        typeof (parsed as {title?: unknown}).title === 'string' &&
        typeof (parsed as {copy?: unknown}).copy === 'string'
      ) {
        const candidate = parsed as {title: string; copy: string};
        if (candidate.title.length > 0 && candidate.copy.length > 0) {
          setLine({title: candidate.title, copy: candidate.copy});
        }
      }
    };
    const now = Date.now();
    if (now - fetchedAtRef.current >= GLANCE_REFRESH_MS) {
      fetchedAtRef.current = now;
      void fetchLine().catch(() => undefined);
    }
    const timer = setInterval(() => {
      if (
        !cancelled &&
        Date.now() - fetchedAtRef.current >= GLANCE_REFRESH_MS
      ) {
        fetchedAtRef.current = Date.now();
        void fetchLine().catch(() => undefined);
      }
    }, 30000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // contextKey refreshes the line when the user's live context shifts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextKey]);
  return line;
}

// Playful local fallbacks when there is nothing urgent and no live frame.
// Real news/weather would need a worker endpoint; these stay on-device and
// rotate on their own so the glance always says something.
const GLANCE_IDLE_LINES: {title: string; copy: string}[] = [
  {
    title: 'Nothing urgent',
    copy: 'The Mac is quiet. A calm moment is still your moment.',
  },
  {
    title: 'Ready when you are',
    copy: 'Say something when you want Omi listening.',
  },
  {
    title: 'All caught up',
    copy: 'Enjoy the calm — Omi will speak up when something matters.',
  },
  {
    title: 'Listening for what matters',
    copy: 'Omi is listening for what matters next.',
  },
];

/**
 * Reads the newest local Recall frame so At a glance can show live "now on
 * your Mac" activity. Polls cheaply while Home is mounted; any failure or a
 * stale frame simply falls back to the day summary.
 */
function useGlanceFrame(): GlanceFrame | null {
  const [frame, setFrame] = useState<GlanceFrame | null>(null);
  useEffect(() => {
    const bridge = NativeModules.OmiRewind as
      | {
          listFrames(input: {
            source: 'captured';
            query: string;
            cursor: string | null;
            limit: number;
          }): Promise<{frames: GlanceFrame[]}>;
        }
      | undefined;
    if (bridge == null) {
      return;
    }
    let retired = false;
    const read = async () => {
      try {
        const page = await bridge!.listFrames({
          source: 'captured',
          query: '',
          cursor: null,
          limit: 1,
        });
        if (!retired) {
          setFrame(page.frames[0] ?? null);
        }
      } catch {
        // Unavailable, auth, or owner change: Home already reports read
        // health; the glance line just falls back.
        if (!retired) {
          setFrame(null);
        }
      }
    };
    void read();
    const timer = setInterval(read, GLANCE_POLL_MS);
    return () => {
      retired = true;
      clearInterval(timer);
    };
  }, []);
  return frame;
}

function glanceLine({
  counts,
  frame,
  minuteOfDay,
}: {
  counts: {conversations: number; memories: number; tasks: number};
  frame: GlanceFrame | null;
  minuteOfDay: number;
}): {title: string; copy: string} {
  if (
    frame != null &&
    Date.now() - frame.capturedAtMs < GLANCE_FRAME_FRESH_MS &&
    frame.appName.length > 0
  ) {
    return {
      title: 'Now on your Mac',
      copy:
        frame.windowTitle.length > 0
          ? `${frame.appName} — ${frame.windowTitle}`
          : frame.appName,
    };
  }
  const total =
    counts.conversations + counts.memories + counts.tasks > 0 || frame != null;
  if (total) {
    const parts: string[] = [];
    if (counts.conversations > 0) {
      parts.push(
        `${counts.conversations} conversation${
          counts.conversations === 1 ? '' : 's'
        }`,
      );
    }
    if (counts.memories > 0) {
      parts.push(
        `${counts.memories} memor${counts.memories === 1 ? 'y' : 'ies'}`,
      );
    }
    if (counts.tasks > 0) {
      parts.push(`${counts.tasks} task${counts.tasks === 1 ? '' : 's'}`);
    }
    return {
      title: 'Your day so far',
      copy: parts.length
        ? parts.join(', ') + ' captured.'
        : 'Captures on this Mac only so far.',
    };
  }
  return GLANCE_IDLE_LINES[
    Math.floor(minuteOfDay / 3) % GLANCE_IDLE_LINES.length
  ];
}

function GlanceCard({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const frame = useGlanceFrame();
  const [minuteOfDay, setMinuteOfDay] = useState(() => {
    const now = new Date();
    return now.getHours() * 60 + now.getMinutes();
  });
  const mounted = useRef(true);
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      const next = now.getHours() * 60 + now.getMinutes();
      if (mounted.current) {
        setMinuteOfDay(next);
      }
    }, 20000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, []);
  const conversations =
    outcomes?.conversations?.status === 'success'
      ? outcomes.conversations.value.items.length
      : 0;
  const memories =
    outcomes?.memories?.status === 'success'
      ? outcomes.memories.value.items.length
      : 0;
  const tasks =
    outcomes?.tasks?.status === 'success'
      ? outcomes.tasks.value.items.length
      : 0;
  const remote = useRemoteGlanceLine({
    counts: {conversations, memories, tasks},
    frame,
  });
  const line =
    remote ??
    glanceLine({
      counts: {conversations, memories, tasks},
      frame,
      minuteOfDay,
    });
  return (
    <View accessibilityLabel="At a glance">
      <PageHeading title={line.title} subtitle={line.copy} />
    </View>
  );
}

export function DesktopReadBanner({
  onRefresh,
  readsPhase,
}: {
  onRefresh: () => void;
  readsPhase: ReadsPhase;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  if (readsPhase === 'initial-loading' || readsPhase === 'refreshing') {
    return (
      <View accessibilityLabel="Reading your day" style={styles.banner}>
        <ActivityIndicator color={token.color.inkMuted} size="small" />
        <Text style={styles.bannerText}>Reading your day…</Text>
      </View>
    );
  }
  if (
    readsPhase === 'unavailable' ||
    readsPhase === 'saved-but-refresh-failed'
  ) {
    return (
      <FocusPressable
        accessibilityLabel="Try again"
        accessibilityRole="button"
        onPress={onRefresh}
        style={({pressed}) => [styles.banner, pressed && styles.pressed]}>
        <Text style={styles.bannerText}>
          Some of your history isn't loaded yet.
        </Text>
        <Text style={styles.bannerAction}>Try again</Text>
      </FocusPressable>
    );
  }
  return null;
}

export function DesktopHome({
  draft,
  onRefresh,
  exploreDone = null,
  onExploreGuide,
  onOpenTasks,
  onOpenConversations,
  outcomes,
  reads,
  readsPhase,
}: Props) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const [wide, setWide] = useState(false);
  const query = draft.trim();
  const currents = useMemo(() => {
    return reads.filter(item => {
      if (item.kind === 'task') {
        return false;
      }
      return matchesSearchQuery(item.searchableText, query);
    });
  }, [query, reads]);
  const tasksOutcome = outcomes?.tasks ?? null;
  const visibleTasks = (
    tasksOutcome?.status === 'success' ? tasksOutcome.value.items : []
  ).filter(item => matchesSearchQuery(item.searchableText, query));
  // Only a successful empty read may claim emptiness. An unsettled read says
  // so plainly; a failed read surfaces its error — except a projection the
  // dev backend legitimately cannot serve yet, which reads as plain empty so
  // the card never shows a plumbing sentence.
  const isProjectionStub = (error: string) =>
    error === desktopProjectionUnavailableCopy;
  const tasksEmptyCopy =
    tasksOutcome === null
      ? 'Loading…'
      : tasksOutcome.status === 'error'
      ? isProjectionStub(tasksOutcome.error)
        ? 'No tasks yet'
        : tasksOutcome.error
      : query !== ''
      ? 'No tasks match this search.'
      : 'No tasks yet';
  const conversationsOutcome = outcomes?.conversations ?? null;
  const memoriesOutcome = outcomes?.memories ?? null;
  const currentsError = [conversationsOutcome, memoriesOutcome].find(
    outcome => outcome?.status === 'error',
  );
  const currentsEmptyCopy =
    conversationsOutcome === null || memoriesOutcome === null
      ? 'Loading…'
      : currentsError?.status === 'error'
      ? isProjectionStub(currentsError.error)
        ? 'Nothing captured yet'
        : currentsError.error
      : query !== ''
      ? 'Nothing captured matches this search.'
      : 'Nothing captured yet.';
  return (
    <View style={styles.home}>
      <DesktopReadBanner onRefresh={onRefresh} readsPhase={readsPhase} />
      <ScrollFade visible style={styles.scroll}>
        <ScrollView
          scrollEventThrottle={16}
          contentContainerStyle={styles.listContent}
          style={styles.list}>
          <GlanceCard outcomes={outcomes} />
          {exploreDone !== null &&
          exploreDone.size < EXPLORE_CHECKLIST.length ? (
            <View accessibilityLabel="Home explore" style={styles.section}>
              <View style={styles.sectionHeader}>
                <SectionTitle>Getting started</SectionTitle>
              </View>
              {EXPLORE_CHECKLIST.map(item => {
                const done = exploreDone.has(item.id);
                return (
                  <FocusPressable
                    key={item.id}
                    accessibilityRole="button"
                    accessibilityLabel={`Guide: ${item.label}`}
                    onPress={() => onExploreGuide?.(item.id)}
                    style={({pressed}) => [
                      styles.exploreRow,
                      pressed && styles.pressed,
                    ]}>
                    <View
                      style={[
                        styles.exploreTick,
                        done && styles.exploreTickDone,
                      ]}>
                      {done ? (
                        <MaterialIcon
                          name="check"
                          size={13}
                          color={token.color.inkMuted}
                        />
                      ) : null}
                    </View>
                    <Text
                      style={[
                        styles.exploreLabel,
                        done && styles.exploreLabelDone,
                      ]}>
                      {item.label}
                    </Text>
                  </FocusPressable>
                );
              })}
            </View>
          ) : null}
          <View
            onLayout={event => setWide(event.nativeEvent.layout.width >= 760)}
            style={[styles.columns, wide && styles.columnsWide]}>
            <View
              accessibilityLabel="Home tasks"
              style={[styles.section, wide && styles.column]}>
              <View style={styles.sectionHeader}>
                <SectionTitle>Tasks</SectionTitle>
                {visibleTasks.length > 0 &&
                tasksOutcome?.status === 'success' &&
                readsPhase !== 'initial-loading' &&
                readsPhase !== 'refreshing' ? (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel={
                      query ? 'Open tasks' : 'Show more tasks'
                    }
                    onPress={onOpenTasks}>
                    <Text style={styles.bannerAction}>
                      {query ? 'Open tasks' : 'Show more'}
                    </Text>
                  </FocusPressable>
                ) : null}
              </View>
              {visibleTasks.length > 0 ? (
                visibleTasks.slice(0, 3).map(item => (
                  <ShippingListInsert itemKey={item.id} key={item.id}>
                    <TaskRow item={item} />
                  </ShippingListInsert>
                ))
              ) : (
                <EmptyCopy>{tasksEmptyCopy}</EmptyCopy>
              )}
              {tasksOutcome?.status === 'success' &&
              !tasksOutcome.value.page.hasMore ? (
                <ReadStatus label="Tasks" mac page={tasksOutcome.value.page} />
              ) : null}
            </View>
            <View
              accessibilityLabel="Home currents"
              style={[styles.section, wide && styles.column]}>
              <View style={styles.sectionHeader}>
                <SectionTitle>Conversations & memories</SectionTitle>
                {currents.length > 0 &&
                conversationsOutcome?.status === 'success' &&
                !currentsError &&
                readsPhase !== 'initial-loading' &&
                readsPhase !== 'refreshing' ? (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel={
                      query ? 'Open conversations' : 'Show more conversations'
                    }
                    onPress={onOpenConversations}>
                    <Text style={styles.bannerAction}>
                      {query ? 'Open conversations' : 'Show more'}
                    </Text>
                  </FocusPressable>
                ) : null}
              </View>
              {currents.length > 0 ? (
                currents.slice(0, 3).map(item => (
                  <ShippingListInsert
                    itemKey={`${item.kind}-${item.id}`}
                    key={`${item.kind}-${item.id}`}>
                    <ReadRow item={item} />
                  </ShippingListInsert>
                ))
              ) : (
                <EmptyCopy>{currentsEmptyCopy}</EmptyCopy>
              )}
              {conversationsOutcome?.status === 'success' &&
              !conversationsOutcome.value.page.hasMore ? (
                <ReadStatus
                  label="Conversations"
                  mac
                  page={conversationsOutcome.value.page}
                />
              ) : null}
              {memoriesOutcome?.status === 'success' &&
              !memoriesOutcome.value.page.hasMore ? (
                <ReadStatus
                  label="Memories"
                  mac
                  page={memoriesOutcome.value.page}
                />
              ) : null}
            </View>
          </View>
        </ScrollView>
      </ScrollFade>
    </View>
  );
}

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    scroll: {flex: 1},
    home: {flex: 1, gap: 12},
    columns: {gap: 16, marginBottom: 16},
    columnsWide: {flexDirection: 'row'},
    column: {flex: 1, minWidth: 0},
    exploreRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      paddingVertical: 7,
      paddingRight: 8,
    },
    exploreTick: {
      width: 22,
      height: 22,
      borderRadius: 11,
      borderWidth: 1,
      borderColor: token.color.lineStrong,
      alignItems: 'center',
      justifyContent: 'center',
    },
    exploreTickDone: {
      backgroundColor: token.color.glassSelected,
      borderColor: token.color.line,
    },
    exploreLabel: {
      fontSize: 13,
      color: token.color.ink,
    },
    exploreLabelDone: {color: token.color.inkMuted},
    sectionHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12,
    },
    banner: {
      alignItems: 'center',
      alignSelf: 'stretch',
      flexDirection: 'row',
      gap: 12,
      minHeight: 32,
      width: '100%',
      paddingHorizontal: 24,
      paddingVertical: 6,
    },
    bannerText: {
      color: token.color.inkMuted,
      flex: 1,
      flexShrink: 1,
      fontFamily: token.font,
      fontSize: token.type.meta,
      minWidth: 0,
    },
    bannerAction: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.meta,
      fontWeight: '600',
    },
    pressed: {opacity: 0.78},
    list: {flex: 1},
    section: {
      backgroundColor: token.color.glassStrong,
      borderWidth: 1,
      borderColor: token.color.line,
      borderRadius: 18,
      gap: 12,
      padding: 24,
    },
    listContent: {
      paddingTop: 8,
      paddingBottom: 32,
      paddingHorizontal: 24,
      maxWidth: 1040,
      width: '100%',
      alignSelf: 'center',
      gap: 16,
    },
  });
