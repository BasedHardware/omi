import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';
import 'widgets/conversation_list_item.dart' show conversationRowTitle;
import 'widgets/synced_conversation_list_item.dart';

class SyncedConversationsPage extends StatefulWidget {
  const SyncedConversationsPage({super.key, this.reprocessConversation = reProcessConversationServer});

  /// The existing server reprocess call; replaceable in tests only.
  final Future<ServerConversation?> Function(String conversationId) reprocessConversation;

  @override
  State<SyncedConversationsPage> createState() => _SyncedConversationsPageState();
}

class _SyncedConversationsPageState extends State<SyncedConversationsPage> {
  /// Native presentation only: conversations whose reprocess is in flight, and the results that
  /// replaced them on this page (the original rows keep this state per item).
  final _reprocessing = <String>{};
  final _reprocessed = <String, ServerConversation>{};

  @override
  Widget build(BuildContext context) {
    final classic = _classic(context);
    if (!nativePresentationEnabled) return classic;
    return Consumer<SyncProvider>(builder: (context, syncProvider, _) {
      final l = context.l10n;
      final pointers = syncProvider.syncedConversationsPointers;
      NativeSection section(String id, String title, SyncedConversationType type, {required bool showReprocess}) =>
          NativeSection(
              id,
              [
                for (var i = 0; i < pointers.length; i++)
                  if (pointers[i].type == type) ..._nativeRows(pointers[i], i, showReprocess: showReprocess),
              ],
              title: title);
      final sections = [
        section('synced_updated', l.updatedConversations, SyncedConversationType.updatedConversation,
            showReprocess: true),
        section('synced_new', l.newConversations, SyncedConversationType.newConversation, showReprocess: false),
      ].where((section) => section.rows.isNotEmpty).toList();
      return Scaffold(
        body: IosNativeSurface(
          title: l.processedConversations,
          fallback: classic,
          toolbar: [
            NativeRow('synced_back', l.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          ],
          sections: sections,
        ),
      );
    });
  }

  List<NativeRow> _nativeRows(SyncedConversationPointer pointer, int index, {required bool showReprocess}) {
    final l = context.l10n;
    final original = pointer.conversation;
    final conversation = _reprocessed[original.id] ?? original;
    final busy = _reprocessing.contains(original.id);
    final canReprocess = showReprocess || conversation.discarded;
    final seconds = conversation.transcriptSegments.isEmpty ? 0 : conversation.getDurationInSeconds();
    final time = OmiDateFormat.of(context).time(conversation.startedAt ?? conversation.createdAt);
    final id = 'synced_conversation:$index:${original.id}';
    return [
      NativeRow(id, conversation.isLocked ? l.conversations : conversationRowTitle(context, conversation),
          kind: 'navigation',
          subtitle: busy ? l.processing : (seconds > 0 ? '$time · ${OmiDuration.compact(seconds, l)}' : time),
          options: {if (canReprocess && !busy) 'reprocess': l.reprocessConversation}, action: (value) async {
        if (value == 'reprocess') {
          await _reprocess(original);
        } else {
          _open(pointer);
        }
      }),
      if (canReprocess)
        NativeRow('$id:reprocess', l.reprocessConversation,
            subtitle: busy ? l.processing : '', enabled: !busy, action: (_) => _reprocess(original)),
    ];
  }

  /// The original row's tap: seed the detail owner, record the tap, open the detail page.
  void _open(SyncedConversationPointer pointer) {
    final conversation = pointer.conversation;
    context.read<ConversationDetailProvider>().updateConversation(conversation.id, pointer.key);
    context.read<ConversationProvider>().onConversationTap(conversation.id);
    routeToPage(context, ConversationDetailPage(conversation: conversation, isFromOnboarding: false));
  }

  /// Reprocesses through the existing server call and hands the result to [ConversationProvider].
  /// A result for a previous account session is dropped.
  Future<void> _reprocess(ServerConversation conversation) async {
    if (_reprocessing.contains(conversation.id)) return;
    final owner = AuthService.instance.captureSessionSnapshot();
    setState(() => _reprocessing.add(conversation.id));
    try {
      final result = await widget.reprocessConversation(conversation.id);
      if (!mounted || owner == null || !AuthService.instance.isSessionSnapshotCurrent(owner)) return;
      if (result != null) {
        _reprocessed[conversation.id] = result;
        context.read<ConversationProvider>().updateSyncedConversation(result);
      }
    } finally {
      if (mounted) setState(() => _reprocessing.remove(conversation.id));
    }
  }

  Widget _classic(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.l10n.processedConversations),
        backgroundColor: OmiColors.surface0,
      ),
      backgroundColor: OmiColors.surface0,
      body: Consumer<SyncProvider>(
        builder: (context, syncProvider, child) {
          return SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ConversationsListWidget(
                  conversations: syncProvider.syncedConversationsPointers
                      .where((e) => e.type == SyncedConversationType.updatedConversation)
                      .toList(),
                  title: context.l10n.updatedConversations,
                  showReprocess: true,
                ),
                ConversationsListWidget(
                  conversations: syncProvider.syncedConversationsPointers
                      .where((e) => e.type == SyncedConversationType.newConversation)
                      .toList(),
                  title: context.l10n.newConversations,
                  showReprocess: false,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class ConversationsListWidget extends StatelessWidget {
  final List<SyncedConversationPointer> conversations;
  final String title;
  final bool showReprocess;
  const ConversationsListWidget({
    super.key,
    required this.conversations,
    required this.title,
    required this.showReprocess,
  });

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty) {
      return const SizedBox();
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const SizedBox(height: 18),
        Text(title, style: TextStyle(color: OmiColors.textPrimary, fontSize: 20)),
        const SizedBox(height: 10),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemBuilder: (ctx, i) {
            var convo = conversations[i];
            return SyncedConversationListItem(
              conversation: convo.conversation,
              date: convo.key,
              conversationIdx: convo.index,
              showReprocess: showReprocess,
            );
          },
          separatorBuilder: (ctx, i) {
            return const SizedBox(height: 10);
          },
          itemCount: conversations.length,
        ),
      ],
    );
  }
}
