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
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// A parsed in-app link (`/conversation/abc?share=1`, `/apps/xyz`, `/settings/data-privacy`) as
/// notifications, quick actions and app links deliver it to the home shell.
@immutable
class HomeDeepLink {
  const HomeDeepLink(this.alias, {this.id, this.query = const {}});

  /// First path segment: `conversation`, `apps`, `chat`, `settings`, `memories`, …
  final String alias;

  /// Second path segment, when present and not empty.
  final String? id;
  final Map<String, String> query;

  static HomeDeepLink? parse(String? route) {
    if (route == null || route.isEmpty) return null;
    final uri = Uri.tryParse('http://localhost.com${route.startsWith('/') ? '' : '/'}$route');
    final segments = uri?.pathSegments.where((s) => s.isNotEmpty).toList() ?? const <String>[];
    if (segments.isEmpty) return null;
    return HomeDeepLink(
      segments[0],
      id: segments.length > 1 ? segments[1] : null,
      query: uri?.queryParameters ?? const {},
    );
  }

  /// The home tab the link belongs to, so the parent (the tab) shows before the child (the page
  /// pushed over it). Null keeps the current tab.
  int? get tabIndex => switch (alias) {
        'action-items' || 'task' => HomeProvider.tasksTab,
        'memories' || 'facts' || 'memory' || 'search' || 'conversations' || 'conversation' => HomeProvider.homeTab,
        _ => null,
      };
}

/// Opens [link] on top of the home shell whose [context] is given: parent first (the tab, or the
/// Settings sheet), then the child page; a link to something that no longer exists says so instead
/// of doing nothing (nav #18). [openSettings] shows the Settings sheet and resolves when it closes.
/// [openSearch] shows the search overlay, with a query when the link carries one.
/// Resolves once the destination is on screen (pushed), not when it is closed.
Future<void> openHomeDeepLink(
  BuildContext context,
  HomeDeepLink link, {
  required Future<void> Function() openSettings,
  Future<void> Function({String? query})? openSearch,
  Future<ActionItemWithMetadata?> Function(String)? taskById,
  void Function(ActionItemWithMetadata)? onTaskOpened,
  Future<Memory?> Function(String)? memoryById,
  void Function(Memory)? onMemoryOpened,
  void Function()? onItemUnavailable,
}) async {
  final id = link.id;
  switch (link.alias) {
    case 'conversations':
      context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
    case 'action-items':
      context.read<HomeProvider>().setIndex(HomeProvider.tasksTab);
    case 'memory':
      if (id == null) return;
      final provider = context.read<MemoriesProvider>();
      final memory = await (memoryById?.call(id) ?? _resolveIndexedMemoryById(id));
      if (!context.mounted) return;
      if (memory == null) {
        if (onItemUnavailable != null) {
          onItemUnavailable();
        } else {
          OmiFeedback.info(context, context.l10n.somethingWentWrong);
        }
      } else if (onMemoryOpened != null) {
        onMemoryOpened(memory);
      } else {
        unawaited(showMemoryQuickEditSheet(context, memory, provider, readOnly: true));
      }
    case 'task':
      if (id == null) return;
      final ActionItemWithMetadata? task;
      if (taskById != null) {
        task = await taskById(id);
      } else {
        final uid = FirebaseAuth.instance.currentUser?.uid;
        if (uid == null) return;
        final result = await action_items_api.ActionItemsApi(baseUrl: Env.apiBaseUrl ?? '').getById(id);
        task = FirebaseAuth.instance.currentUser?.uid == uid && result is ApiSuccess<ActionItemWithMetadata>
            ? result.data
            : null;
      }
      if (!context.mounted) return;
      if (task == null || !siriTaskIsIndexable(task, DateTime.now())) {
        if (onItemUnavailable != null) {
          onItemUnavailable();
        } else {
          OmiFeedback.info(context, context.l10n.somethingWentWrong);
        }
      } else if (onTaskOpened != null) {
        onTaskOpened(task);
      } else {
        unawaited(showActionItemFormSheet(context, actionItem: task));
      }
    case 'search':
      final query = link.query['q']?.trim() ?? '';
      context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
      // Pushed, not awaited: the overlay is on screen when this resolves.
      unawaited(openSearch?.call(query: query.isEmpty ? null : query));
    case 'apps':
      if (id == null) return;
      final app = await context.read<AppProvider>().getAppFromId(id);
      if (!context.mounted) return;
      if (app == null) {
        OmiFeedback.info(context, context.l10n.appNotFoundOrRemoved);
        return;
      }
      unawaited(routeToPage(context, AppDetailPage(app: app)));
    case 'chat':
      await _prepareChat(context, id);
      if (!context.mounted) return;
      unawaited(
        openChatSheet(context, ChatPage(isPivotBottom: false, initialDraft: link.query['draft'])),
      );
    case 'settings':
      // The sheet is pushed synchronously, so a page pushed next lands on top of it.
      unawaited(openSettings());
      if (id == 'data-privacy') unawaited(routeToPage(context, const DataPrivacyPage()));
      if (id == 'device') unawaited(routeToPage(context, const DeviceSettings()));
    case 'memories':
    case 'facts':
      unawaited(routeToPage(context, const MemoriesPage()));
    case 'conversation':
      if (id == null) return;
      final uid = FirebaseAuth.instance.currentUser?.uid;
      if (uid == null) return;
      final conversation = await getConversationById(id);
      if (!context.mounted) return;
      if (FirebaseAuth.instance.currentUser?.uid != uid || conversation == null) {
        Logger.debug('Conversation not found: $id');
        OmiFeedback.info(context, context.l10n.conversationNotFoundOrDeleted);
        return;
      }
      unawaited(routeToPage(
        context,
        ConversationDetailPage(conversation: conversation, openShareToContactsOnLoad: link.query['share'] == '1'),
      ));
    case 'daily-summary':
      if (id == null) return;
      PlatformManager.instance.analytics.dailySummaryNotificationOpened(
        summaryId: id,
        date: '', // Not in the link; the detail page loads it.
      );
      unawaited(routeToPage(context, DailySummaryDetailPage(summaryId: id)));
    case 'wrapped':
      unawaited(routeToPage(context, const Wrapped2025Page()));
    default:
      // `action-items` only selects its tab; unknown aliases open Home.
      return;
  }
}

/// The backend has no memory-by-id read endpoint. Walk its owner-wide All
/// cursor, independent of the active Memories view or device filter. Incomplete
/// reads never turn an unseen id into a claim that the memory was deleted.
Future<Memory?> _resolveIndexedMemoryById(String id) async {
  final uid = FirebaseAuth.instance.currentUser?.uid;
  if (uid == null) return null;
  return resolveIndexedMemoryById(id, uid: uid, ownerIsCurrent: () => FirebaseAuth.instance.currentUser?.uid == uid);
}

typedef IndexedMemoryPageFetcher = Future<memories_api.GetMemoriesResult> Function({
  required int limit,
  required int offset,
  String? cursor,
});

/// Resolve a Siri memory against owner-wide pages, including rows hidden by
/// useful-now, this-device, search, or the first visible page.
Future<Memory?> resolveIndexedMemoryById(
  String id, {
  required String uid,
  required bool Function() ownerIsCurrent,
  IndexedMemoryPageFetcher? fetchPage,
}) async {
  const limit = 500;
  var offset = 0;
  String? cursor;
  final seenCursors = <String>{};
  for (var page = 0; page < 100; page++) {
    final result = await (fetchPage?.call(limit: limit, offset: cursor == null ? offset : 0, cursor: cursor) ??
        memories_api.getMemoriesResult(
          limit: limit,
          offset: cursor == null ? offset : 0,
          cursor: cursor,
          view: memories_api.MemoryReadView.all,
          forceView: true,
        ));
    if (!ownerIsCurrent() || !result.ok || result.truncated) return null;
    for (final row in result.memories) {
      if (row.id == id && row.uid == uid && siriMemoryIsIndexable(row, DateTime.now())) return row;
    }
    final next = result.nextCursor;
    if (next != null) {
      if (!seenCursors.add(next)) return null;
      cursor = next;
    } else if (cursor != null || result.memories.length < limit) {
      return null;
    } else {
      offset += result.memories.length;
    }
  }
  return null;
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
