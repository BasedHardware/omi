import React, {useEffect, useState} from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import Archive from 'lucide-react-native/icons/archive';
import CalendarDays from 'lucide-react-native/icons/calendar-days';
import FileText from 'lucide-react-native/icons/file-text';
import Folder from 'lucide-react-native/icons/folder';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Sparkles from 'lucide-react-native/icons/sparkles';
import {loadConnectors, type CloudApp} from '../desktopCloudClient';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import {omiBackend} from '../omiNative';
import {ShippingListInsert} from './ShippingStage';
import {ConversationRow, EmptyCopy, TaskRow} from './DesktopRows';
import type {DesktopSession} from './desktopChrome';
import {desktopTokens as token} from './tokens';

export function LibraryPage({
  outcomes,
}: {
  outcomes: DesktopReadOutcomes | null;
}) {
  const conversations =
    outcomes?.conversations.status === 'success'
      ? outcomes.conversations.value.items
      : [];
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
          <EmptyCopy>Nothing captured in this window yet.</EmptyCopy>
        )}
      </ScrollView>
    </View>
  );
}

export function TasksPage({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const tasks =
    outcomes?.tasks.status === 'success' ? outcomes.tasks.value.items : [];
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
          <EmptyCopy>No tasks yet</EmptyCopy>
        )}
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

const importPlaceholders: AppTileModel[] = [
  {
    id: 'calendar',
    name: 'Calendar',
    source: 'Google Calendar',
    status: 'Not connected',
    Icon: CalendarDays,
  },
  {
    id: 'email',
    name: 'Email',
    source: 'Gmail',
    status: 'Not connected',
    Icon: Archive,
  },
  {
    id: 'local-files',
    name: 'Local files',
    source: 'This Mac',
    status: 'Not connected',
    Icon: Folder,
  },
  {
    id: 'apple-notes',
    name: 'Apple Notes',
    source: 'Private notes',
    status: 'Not connected',
    Icon: FileText,
  },
  {
    id: 'x-twitter',
    name: 'X (Twitter)',
    source: 'Your posts and bookmarks',
    status: 'Not connected',
    Icon: Sparkles,
  },
  {
    id: 'chatgpt',
    name: 'ChatGPT',
    source: 'Memory import',
    status: 'Not connected',
    Icon: Puzzle,
  },
];

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
  const [tiles, setTiles] = useState<AppTileModel[]>(importPlaceholders);
  useEffect(() => {
    if (session !== 'ready') {
      setTiles(importPlaceholders);
      return;
    }
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      setTiles(importPlaceholders);
      return;
    }
    let active = true;
    loadConnectors(backend)
      .then(snapshot => {
        if (!active) {
          return;
        }
        setTiles(
          snapshot.apps.length > 0
            ? tilesFromCatalog(snapshot.apps)
            : importPlaceholders,
        );
      })
      .catch(() => {
        if (active) {
          setTiles(importPlaceholders);
        }
      });
    return () => {
      active = false;
    };
  }, [session]);
  return (
    <View style={styles.page}>
      <ScrollView contentContainerStyle={styles.appGrid}>
        {tiles.map(item => (
          <AppTile item={item} key={item.id} />
        ))}
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
