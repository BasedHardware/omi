import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum ChatHistoryAction { newChat, open, app }

class ChatHistoryChoice {
  const ChatHistoryChoice(this.action, {this.session, this.app});
  final ChatHistoryAction action;
  final ChatSessionSummary? session;
  final App? app;
}

class PastChatsPage extends StatefulWidget {
  const PastChatsPage({super.key});
  @override
  State<PastChatsPage> createState() => _PastChatsPageState();
}

class _PastChatsPageState extends State<PastChatsPage> {
  final _sessions = <ChatSessionSummary>[];
  bool _loading = true;
  bool _hasMore = false;
  bool _failed = false;
  bool _degraded = false;
  bool _retryMore = false;
  int _offset = 0;
  int _request = 0;
  String? _deleting;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool more = false}) async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _failed = false;
      _retryMore = more;
    });
    final result = await context.read<MessageProvider>().chatSessionsApi.list(offset: more ? _offset : 0);
    if (!mounted || request != _request) return;
    setState(() {
      _loading = false;
      if (result is ApiFailure<List<ChatSessionSummary>>) {
        _failed = true;
        return;
      }
      final loaded = result as ApiSuccess<List<ChatSessionSummary>>;
      final rows = loaded.data;
      _degraded = loaded.rejectedRows > 0;
      if (!more) {
        _sessions.clear();
        _offset = 0;
      }
      // Offset counts server rows, including rejected/empty rows; visible rows are only a projection.
      final received = rows.length + loaded.rejectedRows;
      _offset += received;
      _hasMore = received == 50;
      final ids = _sessions.map((s) => s.id).toSet();
      _sessions.addAll(rows.where((s) => s.hasContent && ids.add(s.id)));
    });
  }

  void _choose(ChatHistoryChoice choice) {
    if (!context.read<MessageProvider>().canSwitchChat || _deleting != null) return;
    OmiHaptics.selection();
    Navigator.of(context).pop(choice);
  }

  Future<void> _delete(ChatSessionSummary session) async {
    final l10n = context.l10n;
    final provider = context.read<MessageProvider>();
    if (!provider.canSwitchChat || _deleting != null) return;
    final confirmed = await showOmiConfirm(context,
        title: l10n.deleteChatQuestion,
        message: l10n.deleteChatMessage,
        confirmLabel: l10n.deleteChat,
        destructive: true);
    if (!mounted || !confirmed || !provider.canSwitchChat) return;
    setState(() => _deleting = session.id);
    final result = await provider.deleteChatSession(session.id);
    if (!mounted) return;
    setState(() => _deleting = null);
    if (!result) {
      OmiFeedback.error(context, l10n.somethingWentWrong);
      return;
    }
    await _load();
  }

  String _title(ChatSessionSummary session) => session.hasTitle
      ? session.title.trim()
      : session.preview.trim().isNotEmpty
          ? session.preview.trim().split('\n').first
          : context.l10n.newChat;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<MessageProvider>();
    final enabled = provider.canSwitchChat && _deleting == null;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.pastChats)),
      body: RefreshIndicator(
        onRefresh: _load,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: ListView(
          key: const Key('past_chats'),
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(OmiSpacing.lg),
          children: [
            _HistoryRow(
                key: const Key('past_chats_new'),
                title: l10n.newChat,
                detail: l10n.startFresh,
                onTap: enabled ? () => _choose(const ChatHistoryChoice(ChatHistoryAction.newChat)) : null),
            if (provider.chatApps.isNotEmpty) ...[
              Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.lg, bottom: OmiSpacing.xs),
                  child: Text(l10n.appsAskWith, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
              for (final app in provider.chatApps)
                _HistoryRow(
                    key: ValueKey('past_chats_app_${app.id}'),
                    title: app.getName(),
                    detail: app.description,
                    onTap: enabled ? () => _choose(ChatHistoryChoice(ChatHistoryAction.app, app: app)) : null),
            ],
            for (final session in _sessions)
              _HistoryRow(
                key: ValueKey('past_chat_${session.id}'),
                title: _title(session),
                detail: OmiDateFormat.of(context).timestamp(session.updatedAt),
                busy: _deleting == session.id,
                onTap: enabled ? () => _choose(ChatHistoryChoice(ChatHistoryAction.open, session: session)) : null,
                onLongPress: enabled
                    ? () => showOmiRowMenu(context, title: _title(session), actions: [
                          OmiMenuAction(
                              icon: Icons.open_in_new,
                              label: l10n.open,
                              onSelected: () => _choose(ChatHistoryChoice(ChatHistoryAction.open, session: session))),
                          OmiMenuAction(
                              icon: Icons.delete_outline,
                              label: l10n.deleteChat,
                              isDestructive: true,
                              onSelected: () => _delete(session)),
                        ])
                    : null,
              ),
            if (_loading)
              const Padding(padding: EdgeInsets.all(OmiSpacing.xl), child: Center(child: OmiSpinner()))
            else if (_failed || _degraded)
              OmiErrorState(message: l10n.somethingWentWrong, onRetry: () => _load(more: _failed && _retryMore))
            else if (_sessions.isEmpty)
              Padding(
                  padding: const EdgeInsets.symmetric(vertical: OmiSpacing.lg),
                  child: Text(l10n.noPastChats, style: OmiType.body.copyWith(color: OmiColors.textSecondary))),
            if (_hasMore && !_loading && !_failed)
              TextButton(
                  key: const Key('past_chats_more'), onPressed: () => _load(more: true), child: Text(l10n.showMore)),
          ],
        ),
      ),
    );
  }
}

class _HistoryRow extends StatelessWidget {
  const _HistoryRow(
      {super.key, required this.title, required this.detail, this.onTap, this.onLongPress, this.busy = false});
  final String title;
  final String detail;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final bool busy;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        onLongPress: onLongPress,
        child: Container(
          constraints: const BoxConstraints(minHeight: 56),
          padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
          decoration: BoxDecoration(border: Border(bottom: BorderSide(color: OmiColors.border))),
          child: Row(children: [
            Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.body.copyWith(fontWeight: FontWeight.w500)),
              const SizedBox(height: OmiSpacing.xxs),
              Text(detail,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ])),
            if (busy) const OmiSpinner(size: OmiSpinnerSize.small),
          ]),
        ),
      );
}
