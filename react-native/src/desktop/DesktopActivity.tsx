import React, {useEffect, useState} from 'react';
import {NativeModules, StyleSheet, Text, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {MaterialIcon} from '../ui/MaterialIcon';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';

import {DesktopReadBanner, GlanceCard} from './DesktopHome';
import {EXPLORE_CHECKLIST, type ExploreCheck} from './exploreChecklist';
import {groupRewindFrames} from './rewindTimeline';
import {SectionTitle} from './DesktopRows';
import {
  UnifiedTimeline,
  type ActivityFilter,
  type CaptureGroupSummary,
} from './timeline/UnifiedTimeline';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';

// The Home page: one Activity timeline of conversations, recall captures, and
// tasks. The old per-surface pages became filters here; Recall stays a real
// page because it is the detail viewer for captures.
const ACTIVITY_FILTERS: {id: ActivityFilter; label: string}[] = [
  {id: 'all', label: 'All'},
  {id: 'conversations', label: 'Conversations'},
  {id: 'recall', label: 'Recall'},
  {id: 'tasks', label: 'Tasks'},
];

export const ACTIVITY_CAPTURE_PAGE = 60;

/**
 * Newest local capture groups for the unified feed. Only page one: the feed
 * interleaves them with cloud outcomes, and Recall owns deep capture history.
 */
function useActivityCaptures(revision: number): CaptureGroupSummary[] {
  const [captures, setCaptures] = useState<CaptureGroupSummary[]>([]);
  useEffect(() => {
    const bridge = NativeModules.OmiRewind as
      | {
          listFrames(input: {
            source: 'captured';
            query: string;
            cursor: string | null;
            limit: number;
          }): Promise<{
            frames: {
              id: string;
              capturedAtMs: number;
              appName: string;
              windowTitle: string;
            }[];
          }>;
        }
      | undefined;
    if (bridge == null) {
      return;
    }
    let retired = false;
    bridge
      .listFrames({
        source: 'captured',
        query: '',
        cursor: null,
        limit: ACTIVITY_CAPTURE_PAGE,
      })
      .then(page => {
        if (retired) {
          return;
        }
        setCaptures(
          groupRewindFrames(page.frames).map(group => ({
            id: group.id,
            title: group.windowTitle.trim() || group.appName,
            appName: group.appName,
            capturedAtMs: group.capturedAtMs,
            count: group.count,
          })),
        );
      })
      .catch(() => {
        // Recall reports capture failures on its own page; the timeline just
        // shows what it can.
      });
    return () => {
      retired = true;
    };
  }, [revision]);
  return captures;
}

export function DesktopActivity({
  captureRevision,
  exploreDone = null,
  filter,
  onCapturePress,
  onExploreItem,
  onFilterChange,
  onRefresh,
  outcomes,
  query,
  readsPhase,
}: {
  captureRevision: number;
  exploreDone?: Set<ExploreCheck> | null;
  filter: ActivityFilter;
  onCapturePress: (capture: CaptureGroupSummary) => void;
  onExploreItem: (check: ExploreCheck) => void;
  onFilterChange: (filter: ActivityFilter) => void;
  onRefresh: () => void;
  outcomes: DesktopReadOutcomes | null;
  query: string;
  readsPhase: ReadsPhase;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const captures = useActivityCaptures(captureRevision);
  return (
    <View style={styles.root} accessibilityLabel="Activity page">
      <DesktopReadBanner onRefresh={onRefresh} readsPhase={readsPhase} />
      <UnifiedTimeline
        captures={captures}
        filter={filter}
        header={
          <View>
            <GlanceCard outcomes={outcomes} />
            <View
              accessibilityLabel="Activity filters"
              accessibilityRole="tablist"
              style={styles.filters}>
              {ACTIVITY_FILTERS.map(item => {
                const selected = item.id === filter;
                return (
                  <FocusPressable
                    key={item.id}
                    accessibilityLabel={`Filter ${item.label}`}
                    accessibilityRole="button"
                    accessibilityState={{selected}}
                    onPress={() => onFilterChange(item.id)}
                    style={({pressed}) => [
                      styles.filter,
                      selected && styles.filterSelected,
                      pressed && styles.pressed,
                    ]}>
                    <Text
                      style={[
                        styles.filterText,
                        selected && styles.filterTextSelected,
                      ]}>
                      {item.label}
                    </Text>
                  </FocusPressable>
                );
              })}
            </View>
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
                      onPress={() => onExploreItem(item.id)}
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
          </View>
        }
        loading={readsPhase === 'initial-loading'}
        onOpenEntry={entry => {
          if (entry.kind === 'capture') {
            const capture = captures.find(
              item => `capture-${item.id}` === entry.id,
            );
            if (capture !== undefined) {
              onCapturePress(capture);
            }
          }
        }}
        outcomes={outcomes}
        query={query}
      />
    </View>
  );
}

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    root: {flex: 1},
    filters: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
      marginBottom: 4,
      marginTop: 14,
    },
    filter: {
      borderRadius: token.radius.chip,
      borderWidth: 1,
      borderColor: token.color.line,
      paddingHorizontal: 14,
      paddingVertical: 7,
      backgroundColor: token.color.glassQuiet,
    },
    filterSelected: {
      backgroundColor: token.color.glassSelected,
      borderColor: token.color.ink,
    },
    filterText: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 12,
      fontWeight: '600',
    },
    filterTextSelected: {color: token.color.ink},
    section: {
      gap: 4,
      marginTop: 14,
    },
    sectionHeader: {marginBottom: 4},
    exploreRow: {
      alignItems: 'center',
      borderRadius: 10,
      flexDirection: 'row',
      gap: 10,
      paddingVertical: 7,
      paddingHorizontal: 6,
    },
    exploreTick: {
      alignItems: 'center',
      borderRadius: 7,
      borderWidth: 1,
      borderColor: token.color.inkFaint,
      height: 18,
      justifyContent: 'center',
      width: 18,
    },
    exploreTickDone: {
      backgroundColor: token.color.glassSelected,
      borderColor: token.color.glassSelected,
    },
    exploreLabel: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.body,
    },
    exploreLabelDone: {color: token.color.inkMuted},
    pressed: {opacity: 0.7},
  });
