import React from 'react';
import {Text, View} from 'react-native';
import type {
  DesktopReadProjection,
  DomainReadOutcome,
  ReadPageState,
} from '../desktopReadClient';
import {styles} from './styles';

export function readStatusCopy(
  label: string,
  page: ReadPageState,
): string | null {
  if (page.complete && page.completenessStatus === 'complete') {
    return null;
  }
  if (!page.hasMore && page.completenessStatus === 'unknown') {
    return null;
  }
  if (page.hasMore) {
    return page.nextCursor === null
      ? `Showing the first 50 ${label.toLowerCase()}. More may be available.`
      : `More ${label.toLowerCase()} are available.`;
  }
  if (page.completenessStatus === 'degraded') {
    return `${label} may be temporarily incomplete.`;
  }
  if (page.completenessStatus === 'partial') {
    return `${label} are a partial view.`;
  }
  return `${label} are incomplete.`;
}

export function emptyLibraryCopy(
  label: string,
  page: ReadPageState | null,
  filtering: boolean,
  filteredCopy: string,
  emptyCopy: string,
): string {
  if (page !== null) {
    const coverage = readStatusCopy(label, page);
    if (coverage !== null) {
      return coverage;
    }
  }
  if (filtering) {
    return filteredCopy;
  }
  return emptyCopy;
}

export function coverageStatusCopy(
  conversationsPage: ReadPageState | null,
  memoriesPage: ReadPageState | null,
  tasksPage: ReadPageState | null = null,
): string | null {
  return (
    (conversationsPage === null
      ? null
      : readStatusCopy('Conversations', conversationsPage)) ??
    (memoriesPage === null ? null : readStatusCopy('Memories', memoriesPage)) ??
    (tasksPage === null ? null : readStatusCopy('Tasks', tasksPage))
  );
}

export function savedDataEmptyTitle(
  conversationsPage: ReadPageState | null,
  memoriesPage: ReadPageState | null,
  tasksPage: ReadPageState | null,
  searching: boolean,
): string {
  return (
    coverageStatusCopy(conversationsPage, memoriesPage, tasksPage) ??
    (searching ? 'No results' : 'Nothing saved yet')
  );
}

export function ReadStatus({
  label,
  page,
  mac = false,
}: {
  label: string;
  page: ReadPageState;
  mac?: boolean;
}) {
  const detail = readStatusCopy(label, page);
  if (detail === null) {
    return null;
  }
  return (
    <View style={[styles.readStatus, mac && styles.macReadStatus]}>
      <Text style={[styles.readStatusText, mac && styles.macReadStatusText]}>
        {detail}
      </Text>
    </View>
  );
}

export function homeSearchPhaseCopy(
  phase:
    | 'initial-loading'
    | 'refreshing'
    | 'saved-but-refresh-failed'
    | 'unavailable',
  mappedUnavailable: string | null,
): string {
  if (phase === 'initial-loading') {
    return 'Loading saved data…';
  }
  if (phase === 'refreshing') {
    return 'Refreshing saved data…';
  }
  if (phase === 'saved-but-refresh-failed') {
    return 'Showing saved data. Could not refresh.';
  }
  return mappedUnavailable ?? 'Saved data is unavailable.';
}

export function OutcomeStatus({
  label,
  outcome,
  mac = false,
}: {
  label: string;
  outcome: DomainReadOutcome<DesktopReadProjection>;
  mac?: boolean;
}) {
  return outcome.status === 'error' ? (
    <View style={[styles.readStatus, mac && styles.macReadStatus]}>
      <Text style={[styles.readStatusText, mac && styles.macReadStatusText]}>
        {outcome.error}
      </Text>
    </View>
  ) : (
    <ReadStatus label={label} mac={mac} page={outcome.value.page} />
  );
}
