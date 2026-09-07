import React from 'react';
import {Text, View} from 'react-native';
import type {
  DesktopReadProjection,
  DomainReadOutcome,
  ReadPageState,
} from '../desktopReadClient';
import {styles} from './styles';

export function ReadStatus({
  label,
  page,
  mac = false,
}: {
  label: string;
  page: ReadPageState;
  mac?: boolean;
}) {
  if (page.complete && page.completenessStatus === 'complete') {
    return null;
  }
  if (!page.hasMore && page.completenessStatus === 'unknown') {
    return null;
  }
  const detail = page.hasMore
    ? page.nextCursor === null
      ? `Showing the first 50 ${label.toLowerCase()}. More may be available.`
      : `More ${label.toLowerCase()} are available.`
    : page.completenessStatus === 'degraded'
    ? `${label} may be temporarily incomplete.`
    : page.completenessStatus === 'partial'
    ? `${label} are a partial view.`
    : `${label} are incomplete.`;
  return (
    <View style={[styles.readStatus, mac && styles.macReadStatus]}>
      <Text style={[styles.readStatusText, mac && styles.macReadStatusText]}>
        {detail}
      </Text>
    </View>
  );
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
        {label} are unavailable.
      </Text>
    </View>
  ) : (
    <ReadStatus label={label} mac={mac} page={outcome.value.page} />
  );
}
