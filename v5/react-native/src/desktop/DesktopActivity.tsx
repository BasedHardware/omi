import React, {useEffect, useState} from 'react';
import {NativeModules, Text, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {MaterialIcon} from '../ui/MaterialIcon';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';

import {DesktopReadBanner} from './DesktopHome';
import {EXPLORE_CHECKLIST, type ExploreCheck} from './exploreChecklist';
import {groupRewindFrames} from './rewindTimeline';
import type {ActivityFilterId, TimelineGrouping} from './desktopChrome';
import {
  UnifiedTimeline,
  type CaptureGroupSummary,
} from './timeline/UnifiedTimeline';
import {OmiSectionLabel} from '../design/primitives';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

// The Home page: one Activity timeline of conversations, recall captures, and
// tasks. Filters and grouping live in the top chrome; this page renders the
// merged feed and the getting-started checklist.
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
  groupBy,
  onCapturePress,
  onExploreItem,
  onRefresh,
  outcomes,
  query,
  readsPhase,
}: {
  captureRevision: number;
  exploreDone?: Set<ExploreCheck> | null;
  filter: ActivityFilterId;
  groupBy: TimelineGrouping;
  onCapturePress: (capture: CaptureGroupSummary) => void;
  onExploreItem: (check: ExploreCheck) => void;
  onRefresh: () => void;
  outcomes: DesktopReadOutcomes | null;
  query: string;
  readsPhase: ReadsPhase;
}) {
  const styles = useOmiStyles(createStyles);
  const theme = useOmiTheme();
  const captures = useActivityCaptures(captureRevision);
  // No page title and no filler hero: the filter chips already say where you
  // are (design language: content before chrome). A read that failed outright
  // becomes the timeline's own page state, so the inline notice only speaks
  // for partial or in-flight reads.
  const showNotice = !(outcomes === null && readsPhase === 'unavailable');
  return (
    <View style={styles.root} accessibilityLabel="Activity page">
      <UnifiedTimeline
        captures={captures}
        filter={filter}
        groupBy={groupBy}
        header={
          <View>
            {showNotice ? (
              <DesktopReadBanner
                onRefresh={onRefresh}
                readsPhase={readsPhase}
              />
            ) : null}
            {exploreDone !== null &&
            exploreDone.size < EXPLORE_CHECKLIST.length ? (
              <View accessibilityLabel="Home explore" style={styles.section}>
                <OmiSectionLabel label="Getting started" />
                {EXPLORE_CHECKLIST.map(item => {
                  const done = exploreDone.has(item.id);
                  return (
                    <FocusPressable
                      key={item.id}
                      accessibilityRole="button"
                      accessibilityLabel={`Guide: ${item.label}`}
                      accessibilityState={{checked: done}}
                      onPress={() => onExploreItem(item.id)}
                      style={state => [
                        styles.exploreRow,
                        (state as {hovered?: boolean}).hovered &&
                          styles.hovered,
                        state.pressed && styles.pressed,
                      ]}>
                      <View
                        style={[
                          styles.exploreTick,
                          done && styles.exploreTickDone,
                        ]}>
                        {done ? (
                          <MaterialIcon
                            name="check"
                            size={12}
                            color={theme.color.onInk}
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
        onRetry={onRefresh}
        outcomes={outcomes}
        query={query}
      />
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  root: {flex: 1},
  section: {marginBottom: t.space.xs},
  exploreRow: {
    alignItems: 'center' as const,
    borderRadius: t.radius.row,
    flexDirection: 'row' as const,
    gap: t.space.md,
    paddingVertical: t.space.sm,
    paddingHorizontal: t.space.sm,
  },
  hovered: {backgroundColor: t.color.fill},
  pressed: {backgroundColor: t.color.fillPressed},
  exploreTick: {
    alignItems: 'center' as const,
    borderRadius: t.radius.pill,
    borderWidth: 1.5,
    borderColor: t.color.hairline,
    height: 18,
    justifyContent: 'center' as const,
    width: 18,
  },
  exploreTickDone: {
    backgroundColor: t.color.inkSecondary,
    borderColor: 'transparent',
  },
  exploreLabel: {...t.type.body, color: t.color.ink},
  exploreLabelDone: {color: t.color.inkSecondary},
});
