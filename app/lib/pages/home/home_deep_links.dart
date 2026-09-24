import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/providers/app_provider.dart';
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
        'action-items' => 2,
        'apps' => 3,
        'memories' || 'facts' => 0,
        _ => null,
      };
}

/// Opens [link] on top of the home shell whose [context] is given: parent first (the tab, or the
/// Settings sheet), then the child page; a link to something that no longer exists says so instead
/// of doing nothing (nav #18). [openSettings] shows the Settings sheet and resolves when it closes.
/// Resolves once the destination is on screen (pushed), not when it is closed.
Future<void> openHomeDeepLink(
  BuildContext context,
  HomeDeepLink link, {
  required Future<void> Function() openSettings,
}) async {
  final id = link.id;
  switch (link.alias) {
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
      // D1: chat is a normal pushed page everywhere.
      unawaited(routeToPage(context, const ChatPage(isPivotBottom: false)));
    case 'settings':
      // The sheet is pushed synchronously, so a page pushed next lands on top of it.
      unawaited(openSettings());
      if (id == 'data-privacy') unawaited(routeToPage(context, const DataPrivacyPage()));
    case 'memories':
    case 'facts':
      unawaited(routeToPage(context, const MemoriesPage()));
    case 'conversation':
      if (id == null) return;
      final conversation = await getConversationById(id);
      if (!context.mounted) return;
      if (conversation == null) {
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
