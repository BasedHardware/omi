import React, {useEffect, useState} from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import Puzzle from 'lucide-react-native/icons/puzzle';
import {loadConnectors, type CloudApp} from '../desktopCloudClient';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import {omiBackend} from '../omiNative';
import {ReadStatus} from '../ui/ReadStatus';
import {ShippingListInsert} from './ShippingStage';
import {ConversationRow, EmptyCopy, TaskRow} from './DesktopRows';
import type {DesktopSession} from './desktopChrome';
import {desktopTokens as token} from './tokens';

export function LibraryPage({
  outcomes,
}: {
  outcomes: DesktopReadOutcomes | null;
}) {
  const outcome = outcomes?.conversations ?? null;
  const conversations =
    outcome?.status === 'success' ? outcome.value.items : [];
  // A failed or unsettled read must never claim "nothing captured": only a
  // successful empty page is an empty library.
  const emptyCopy =
    outcome === null
      ? 'Loading conversations…'
      : outcome.status === 'error'
      ? outcome.error
      : 'Nothing captured in this window yet.';
  return (
    <View style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.listContent}
        style={styles.list}>
        {conversations.length > 0 ? (
          conversations.map(item => (
            <ShippingListInsert itemKey={item.id} key={item.id}>
              <ConversationRow item={item} />
            </ShippingListInsert>
          ))
        ) : (
          <EmptyCopy>{emptyCopy}</EmptyCopy>
        )}
        {outcome?.status === 'success' ? (
          <ReadStatus label="Conversations" mac page={outcome.value.page} />
        ) : null}
      </ScrollView>
    </View>
  );
}

export function TasksPage({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const outcome = outcomes?.tasks ?? null;
  const tasks = outcome?.status === 'success' ? outcome.value.items : [];
  const emptyCopy =
    outcome === null
      ? 'Loading tasks…'
      : outcome.status === 'error'
      ? outcome.error
      : 'No tasks yet';
  return (
    <View style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.listContent}
        style={styles.list}>
        {tasks.length > 0 ? (
          tasks.map(item => (
            <ShippingListInsert itemKey={item.id} key={item.id}>
              <TaskRow item={item} />
            </ShippingListInsert>
          ))
        ) : (
          <EmptyCopy>{emptyCopy}</EmptyCopy>
        )}
        {outcome?.status === 'success' ? (
          <ReadStatus label="Tasks" mac page={outcome.value.page} />
        ) : null}
      </ScrollView>
    </View>
  );
}

type AppTileModel = {
  Icon: typeof Puzzle;
  id: string;
  name: string;
  source: string;
  status: string;
};

function cloudAppStatus(app: CloudApp): string {
  if (app.connectedAccounts.length > 0) {
    return 'Connected';
  }
  if (app.enabled) {
    return 'Installed';
  }
  return 'Not connected';
}

function cloudAppSource(app: CloudApp): string {
  if (app.author.length > 0) {
    return app.author;
  }
  if (app.category.length > 0) {
    return app.category;
  }
  return app.description;
}

function tilesFromCatalog(apps: CloudApp[]): AppTileModel[] {
  return apps.map(app => ({
    Icon: Puzzle,
    id: app.id,
    name: app.name,
    source: cloudAppSource(app),
    status: cloudAppStatus(app),
  }));
}

function AppTile({item}: {item: AppTileModel}) {
  const Icon = item.Icon;
  return (
    <View style={styles.appSlot}>
      <View style={styles.appCard}>
        <View style={styles.appIcon}>
          <Icon color={token.color.ink} size={22} />
        </View>
        <Text style={styles.rowTitle}>{item.name}</Text>
        <Text style={styles.rowMeta}>{item.source}</Text>
        <Text style={styles.appStatus}>{item.status}</Text>
      </View>
    </View>
  );
}

export function AppsPage({session}: {session: DesktopSession}) {
  const [tiles, setTiles] = useState<AppTileModel[] | null>();
  useEffect(() => {
    if (session !== 'ready') {
      setTiles(undefined);
      return;
    }
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      setTiles(null);
      return;
    }
    setTiles(undefined);
    let active = true;
    loadConnectors(backend)
      .then(snapshot => {
        if (!active) {
          return;
        }
        setTiles(tilesFromCatalog(snapshot.apps));
      })
      .catch(() => {
        if (active) {
          setTiles(null);
        }
      });
    return () => {
      active = false;
    };
  }, [session]);
  return (
    <View style={styles.page}>
      <ScrollView contentContainerStyle={styles.appGrid}>
        {tiles === undefined ? (
          <EmptyCopy>Loading apps…</EmptyCopy>
        ) : tiles === null ? (
          <EmptyCopy>Apps could not be loaded.</EmptyCopy>
        ) : tiles.length === 0 ? (
          <EmptyCopy>No apps are available.</EmptyCopy>
        ) : (
          tiles.map(item => <AppTile item={item} key={item.id} />)
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1},
  hubRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 14,
    minHeight: 32,
  },
  hubItem: {
    alignItems: 'center',
    height: 28,
    justifyContent: 'center',
  },
  hubText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  hubTextActive: {color: token.color.ink},
  list: {flex: 1},
  listContent: {paddingBottom: 24, paddingTop: 4},
  pageTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '600',
  },
  tasksHeader: {alignItems: 'center', flexDirection: 'row', gap: 12},
  searchControl: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
    height: 32,
  },
  searchInput: {
    color: token.color.ink,
    flex: 1,
    fontFamily: token.font,
    fontSize: token.type.body,
    height: 32,
    minWidth: 0,
    paddingVertical: 0,
  },
  rowTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '500',
  },
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 2,
  },
  emptyTitle: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.search,
    fontWeight: '400',
    textAlign: 'center',
  },
  centerState: {
    alignItems: 'center',
    flex: 1,
    gap: 8,
    justifyContent: 'center',
    paddingVertical: 40,
  },
  appGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 6,
    paddingTop: 12,
  },
  appSlot: {
    padding: 6,
    width: '50%',
  },
  appCard: {
    aspectRatio: 1,
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    padding: 12,
  },
  appIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderRadius: 12,
    height: 40,
    justifyContent: 'center',
    marginBottom: 12,
    width: 40,
  },
  appStatus: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 12,
  },
});
