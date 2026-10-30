import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/widgets.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/http/api/memories.dart' as memories_api;
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/chat/chat_route.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/home/item_list_sheet.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/share_links.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// One entry of an `/items` link: its kind (`conversation`, `task`, `memory`) and server id.
typedef ItemLinkRef = ({String kind, String id});

/// A parsed in-app link (`/conversation/abc?share=1`, `/apps/xyz`, `/settings/data-privacy`) as
/// notifications, quick actions and app links deliver it to the home shell.
@immutable
class HomeDeepLink {
  const HomeDeepLink(this.alias, {this.id, this.query = const {}, this.rawQuery = ''});

  /// First path segment: `conversation`, `apps`, `chat`, `settings`, `memories`, …
  final String alias;

  /// Second path segment, when present and not empty.
  final String? id;
  final Map<String, String> query;

  /// The query string as given, for links whose repeated keys and their order matter (`/items`).
  final String rawQuery;

  /// The ordered items of an `/items` link (see [parseItemList]).
  List<ItemLinkRef> get itemList => parseItemList(rawQuery);

  static HomeDeepLink? parse(String? route) {
    if (route == null || route.isEmpty) return null;
    final uri = Uri.tryParse('http://localhost.com${route.startsWith('/') ? '' : '/'}$route');
    final segments = uri?.pathSegments.where((s) => s.isNotEmpty).toList() ?? const <String>[];
    if (segments.isEmpty) return null;
    return HomeDeepLink(
      segments[0],
      id: segments.length > 1 ? segments[1] : null,
      query: uri?.queryParameters ?? const {},
      rawQuery: uri?.query ?? '',
    );
  }

  /// Private item links on the share host: `https://h.omi.me/conversation/<id>`,
  /// `/task/<id>`, `/memory/<id>` (also as `omi://h.omi.me/…`, which the web
  /// fallback page uses on iOS). Singular on purpose: the plural
  /// `/conversations/<id>` and `/tasks/<token>` are public share pages with their
  /// own handling. Returns the in-app route, or null for any other link.
  static const itemLinkKinds = {'conversation', 'task', 'memory'};

  ///
  /// `https://h.omi.me/items?conversation=a&task=b&memory=c` is a list of up to [maxListItems]
  /// items in URL order; it routes to `/items?…` with only the recognised pairs kept.
  static String? itemRouteFromAppLink(Uri uri, {String? shareBase}) {
    final hosts = {'h.omi.me', Uri.tryParse(shareBaseUrl(shareBase))?.host};
    if (!hosts.contains(uri.host.toLowerCase())) return null;
    if (uri.scheme != 'https' && uri.scheme != 'omi') return null;
    final segments = uri.pathSegments.where((s) => s.isNotEmpty).toList();
    if (segments.length == 1 && segments[0] == 'items') {
      final items = parseItemList(uri.query);
      if (items.isEmpty) return '/items';
      return '/items?${items.map((i) => '${i.kind}=${Uri.encodeQueryComponent(i.id)}').join('&')}';
    }
    if (segments.length != 2 || !itemLinkKinds.contains(segments[0])) return null;
    return '/${segments[0]}/${Uri.encodeComponent(segments[1])}';
  }

  /// Most items one `/items` link lists; later pairs are ignored.
  static const maxListItems = 10;

  /// Opaque server ids, the same charset as `web/frontend/src/lib/item-link.mjs`.
  /// Anything else is dropped so an id cannot retarget `v1/conversations/$id`.
  static final RegExp itemLinkIdPattern = RegExp(r'^[A-Za-z0-9_-]{1,128}$');

  /// The `(kind, id)` pairs of an `/items` query in the order they appear: repeated keys, one per
  /// item, kinds from [itemLinkKinds]. Unknown keys, ids outside [itemLinkIdPattern], and repeats
  /// are dropped, and the list stops at [maxListItems].
  static List<ItemLinkRef> parseItemList(String query) {
    final items = <ItemLinkRef>[];
    final seen = <String>{};
    for (final pair in query.split('&')) {
      if (items.length >= maxListItems) break;
      final eq = pair.indexOf('=');
      if (eq <= 0) continue;
      final String kind;
      final String id;
      try {
        kind = Uri.decodeQueryComponent(pair.substring(0, eq));
        id = Uri.decodeQueryComponent(pair.substring(eq + 1)).trim();
      } on ArgumentError {
        continue;
      } on FormatException {
        continue;
      }
      if (!itemLinkKinds.contains(kind) || !itemLinkIdPattern.hasMatch(id)) continue;
      if (!seen.add('$kind\u0000$id')) continue;
      items.add((kind: kind, id: id));
    }
    return items;
  }

  /// The home tab the link belongs to, so the parent (the tab) shows before the child (the page
  /// pushed over it). Null keeps the current tab.
  int? get tabIndex => switch (alias) {
        'action-items' || 'task' => HomeProvider.tasksTab,
        'capture' ||
        'memories' ||
        'facts' ||
        'memory' ||
        'search' ||
        'conversations' ||
        'conversation' ||
        'items' =>
          HomeProvider.homeTab,
        _ => null,
      };
}

/// Opens [link] on top of the home shell whose [context] is given: parent first (the tab, or the
/// Settings sheet), then the child page; a link to something that no longer exists says so instead
/// of doing nothing (nav #18). [openSettings] shows the Settings sheet and resolves when it closes.
/// [openSearch] shows the search overlay, with a query when the link carries one.
/// Resolves once the destination is on screen (pushed), not when it is closed.
Future<bool> openHomeDeepLink(
  BuildContext context,
  HomeDeepLink link, {
  required Future<void> Function() openSettings,
  Future<void> Function({String? query})? openSearch,
  Future<ActionItemWithMetadata?> Function(String)? taskById,
  void Function(ActionItemWithMetadata)? onTaskOpened,
  Future<Memory?> Function(String)? memoryById,
  void Function(Memory)? onMemoryOpened,
  void Function()? onItemUnavailable,
  bool Function()? canOpen,
}) async {
  if (canOpen != null && !canOpen()) return false;
  final id = link.id;
  switch (link.alias) {
    case 'capture':
      final capture = context.read<CaptureProvider>();
      context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
      // A card for a recording that has since ended leaves Home on screen.
      if (capture.activeRecordingId == null || capture.activeRecordingId != link.query['recording']) return false;
      unawaited(routeToPage(context, const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript)));
    case 'conversations':
      context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
    case 'action-items':
      context.read<HomeProvider>().setIndex(HomeProvider.tasksTab);
    case 'memory':
      if (id == null) return false;
      final provider = context.read<MemoriesProvider>();
      final memory = await (memoryById?.call(id) ?? _resolveIndexedMemoryById(id));
      if (!context.mounted || (canOpen != null && !canOpen())) return false;
      if (memory == null) {
        if (onItemUnavailable != null) {
          onItemUnavailable();
        } else {
          OmiFeedback.info(context, context.l10n.somethingWentWrong);
        }
        return false;
      } else if (onMemoryOpened != null) {
        onMemoryOpened(memory);
      } else {
        unawaited(showMemoryQuickEditSheet(context, memory, provider, readOnly: true));
      }
    case 'task':
      if (id == null) return false;
      final ActionItemWithMetadata? task;
      if (taskById != null) {
        task = await taskById(id);
      } else {
        final uid = FirebaseAuth.instance.currentUser?.uid;
        if (uid == null) return false;
        final result = await action_items_api.ActionItemsApi(baseUrl: Env.apiBaseUrl ?? '').getById(id);
        task = FirebaseAuth.instance.currentUser?.uid == uid && result is ApiSuccess<ActionItemWithMetadata>
            ? result.data
            : null;
      }
      if (!context.mounted || (canOpen != null && !canOpen())) return false;
      if (task == null || !siriTaskIsIndexable(task, DateTime.now())) {
        if (onItemUnavailable != null) {
          onItemUnavailable();
        } else {
          OmiFeedback.info(context, context.l10n.somethingWentWrong);
        }
        return false;
      } else if (onTaskOpened != null) {
        onTaskOpened(task);
      } else {
        unawaited(showActionItemFormSheet(context, actionItem: task));
      }
    case 'items':
      // The list resolves its rows itself; missing or foreign items show as unavailable rows.
      unawaited(showItemListSheet(context, link.itemList));
    case 'search':
      final query = link.query['q']?.trim() ?? '';
      context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
      // Pushed, not awaited: the overlay is on screen when this resolves.
      unawaited(openSearch?.call(query: query.isEmpty ? null : query));
    case 'apps':
      if (id == null) return false;
      final app = await context.read<AppProvider>().getAppFromId(id);
      if (!context.mounted || (canOpen != null && !canOpen())) return false;
      if (app == null) {
        OmiFeedback.info(context, context.l10n.appNotFoundOrRemoved);
        return false;
      }
      unawaited(routeToPage(context, AppDetailPage(app: app)));
    case 'chat':
      await _prepareChat(context, id);
      if (!context.mounted || (canOpen != null && !canOpen())) return false;
      unawaited(openChatSheet(context, ChatPage(isPivotBottom: false, initialDraft: link.query['draft'])));
    case 'settings':
      // The sheet is pushed synchronously, so a page pushed next lands on top of it.
      unawaited(openSettings());
      if (id == 'data-privacy') unawaited(routeToPage(context, const DataPrivacyPage()));
      if (id == 'device') unawaited(routeToPage(context, const DeviceSettings()));
    case 'memories':
    case 'facts':
      unawaited(routeToPage(context, const MemoriesPage()));
    case 'conversation':
      if (id == null) return false;
      final uid = FirebaseAuth.instance.currentUser?.uid;
      if (uid == null) return false;
      final conversation = await getConversationById(id);
      if (!context.mounted || (canOpen != null && !canOpen())) return false;
      if (FirebaseAuth.instance.currentUser?.uid != uid || conversation == null) {
        Logger.debug('Conversation not found: $id');
        OmiFeedback.info(context, context.l10n.conversationNotFoundOrDeleted);
        return false;
      }
      unawaited(
        routeToPage(
          context,
          ConversationDetailPage(conversation: conversation, openShareToContactsOnLoad: link.query['share'] == '1'),
        ),
      );
    case 'daily-summary':
      if (id == null) return false;
      PlatformManager.instance.analytics.dailySummaryNotificationOpened(
        summaryId: id,
        date: '', // Not in the link; the detail page loads it.
      );
      unawaited(routeToPage(context, DailySummaryDetailPage(summaryId: id)));
    case 'wrapped':
      unawaited(routeToPage(context, const Wrapped2025Page()));
    default:
      // `action-items` only selects its tab; unknown aliases open Home.
      return false;
  }
  return true;
}

/// The backend has no memory-by-id read endpoint. Walk its owner-wide All
/// cursor, independent of the active Memories view or device filter. Incomplete
/// reads never turn an unseen id into a claim that the memory was deleted.
Future<Memory?> _resolveIndexedMemoryById(String id) async {
  final uid = FirebaseAuth.instance.currentUser?.uid;
  if (uid == null) return null;
  return resolveIndexedMemoryById(id, uid: uid, ownerIsCurrent: () => FirebaseAuth.instance.currentUser?.uid == uid);
}

typedef IndexedMemoryPageFetcher = Future<memories_api.GetMemoriesResult> Function(
    {required int limit, required int offset, String? cursor});

/// Resolve a Siri memory against owner-wide pages, including rows hidden by
/// useful-now, this-device, search, or the first visible page.
Future<Memory?> resolveIndexedMemoryById(
  String id, {
  required String uid,
  required bool Function() ownerIsCurrent,
  IndexedMemoryPageFetcher? fetchPage,
}) async {
  final found = await resolveIndexedMemoriesByIds(
    {id},
    uid: uid,
    ownerIsCurrent: ownerIsCurrent,
    fetchPage: fetchPage,
  );
  return found[id];
}

/// [resolveIndexedMemoryById] for several ids in one walk (an `/items` link). Stops once every id
/// is found. A failed, truncated or foreign-owner read ends the walk with what was found so far.
Future<Map<String, Memory>> resolveIndexedMemoriesByIds(
  Set<String> ids, {
  required String uid,
  required bool Function() ownerIsCurrent,
  IndexedMemoryPageFetcher? fetchPage,
}) async {
  const limit = 500;
  final found = <String, Memory>{};
  if (ids.isEmpty) return found;
  var offset = 0;
  String? cursor;
  final seenCursors = <String>{};
  for (var page = 0; page < 100; page++) {
    final result = await (fetchPage?.call(limit: limit, offset: cursor == null ? offset : 0, cursor: cursor) ??
        memories_api.getMemoriesResult(
          limit: limit,
          offset: cursor == null ? offset : 0,
          cursor: cursor,
        ));
    if (!ownerIsCurrent()) return const {};
    if (!result.ok || result.truncated) return found;
    for (final row in result.memories) {
      if (ids.contains(row.id) && row.uid == uid && siriMemoryIsIndexable(row, DateTime.now())) found[row.id] = row;
    }
    if (found.length == ids.length) return found;
    final next = result.nextCursor;
    if (next != null) {
      if (!seenCursors.add(next)) return found;
      cursor = next;
    } else if (cursor != null || result.memories.length < limit) {
      return found;
    } else {
      offset += result.memories.length;
    }
  }
  return found;
}

Future<void> _prepareChat(BuildContext context, String? id) async {
  final messageProvider = context.read<MessageProvider>();
  if (id == null || id.isEmpty) {
    await messageProvider.refreshMessages();
    return;
  }
  final appProvider = context.read<AppProvider>();
  final appId = id != 'omi' ? id : ''; // omi ~ no app selected
  App? selectedApp;
  if (appId.isNotEmpty) selectedApp = await appProvider.getAppFromId(appId);
  appProvider.setSelectedChatAppId(appId);
  await messageProvider.refreshMessages();
  if (messageProvider.messages.isEmpty) messageProvider.sendInitialAppMessage(selectedApp);
}
