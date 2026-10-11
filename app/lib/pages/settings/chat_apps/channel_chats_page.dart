import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/widgets/markdown_message_widget.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_problem.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// A chat app's sessions, shown only after "Show these chats in the Omi app" is on.
///
/// They are separate from Ask Omi: each opens read-only, because replies belong in the chat app.
class ChannelChatsPage extends StatefulWidget {
  const ChannelChatsPage({super.key, required this.linkId, this.api});

  final String linkId;

  /// Injected for tests.
  final ChatSessionsApi? api;

  @override
  State<ChannelChatsPage> createState() => _ChannelChatsPageState();
}

class _ChannelChatsPageState extends State<ChannelChatsPage> {
  late final ChatSessionsApi _api = widget.api ?? ChatSessionsApi();
  ApiResult<List<ChatSessionSummary>>? _result;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _result = null);
    final result = await _api.list(limit: 100);
    if (mounted) setState(() => _result = result);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final link = context.watch<MessagingChannelsProvider>().linkById(widget.linkId);
    final channel = link?.channel;
    final name = channel?.displayName ?? '';
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.chatAppsChannelChats(name))),
      body: switch (_result) {
        null => const OmiLoadingState(),
        ApiFailure(:final problem) =>
          OmiErrorState(message: ChatAppsProblem.fromApi(problem).message(context), onRetry: _load),
        ApiSuccess(:final data) => _list(
            context,
            [
              for (final s in data)
                if (s.channelLinkId == widget.linkId) s
            ],
            channel,
            name),
      },
    );
  }

  Widget _list(BuildContext context, List<ChatSessionSummary> sessions, ChatChannel? channel, String name) {
    final l10n = context.l10n;
    if (sessions.isEmpty) {
      return OmiEmptyState(
        icon: Icons.forum_outlined,
        title: l10n.chatAppsNoChatsTitle,
        message: l10n.chatAppsNoChatsMessage(name),
      );
    }
    final dates = OmiDateFormat.of(context);
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xxl),
        children: [
          OmiSettingsGroup(
            footer: l10n.chatAppsReadOnlyFooter(name),
            children: [
              for (final session in sessions)
                OmiSettingsRow(
                  key: ValueKey('chat_apps_session_${session.id}'),
                  leading: channel == null ? null : ChatAppLogo(channel, size: 28),
                  title: session.hasTitle ? session.title : l10n.chatAppsChatIn(name),
                  subtitle: session.preview.trim().isEmpty
                      ? dates.timestamp(session.updatedAt)
                      : '${dates.timestamp(session.updatedAt)} · ${session.preview.trim()}',
                  onTap: () => routeToPage(
                    context,
                    ChannelTranscriptPage(session: session, channel: channel, api: _api),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// One chat-app session's messages, read-only, with the channel badge and no composer.
class ChannelTranscriptPage extends StatefulWidget {
  const ChannelTranscriptPage({super.key, required this.session, required this.channel, required this.api});

  final ChatSessionSummary session;
  final ChatChannel? channel;
  final ChatSessionsApi api;

  @override
  State<ChannelTranscriptPage> createState() => _ChannelTranscriptPageState();
}

class _ChannelTranscriptPageState extends State<ChannelTranscriptPage> {
  ApiResult<List<ServerMessage>>? _result;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _result = null);
    final result = await widget.api.messages(widget.session.id);
    if (mounted) setState(() => _result = result);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final channel = widget.channel;
    final name = channel?.displayName ?? '';
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(widget.session.hasTitle ? widget.session.title : l10n.chatAppsChatIn(name)),
      ),
      body: Column(
        children: [
          Container(
            key: const ValueKey('chat_apps_read_only_banner'),
            margin: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            child: Row(
              children: [
                if (channel != null) ...[ChatAppLogo(channel, size: 20), const SizedBox(width: OmiSpacing.xs)],
                Expanded(
                  child: Text(l10n.chatAppsReadOnlyBanner(name),
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                ),
              ],
            ),
          ),
          Expanded(
            child: switch (_result) {
              null => const OmiLoadingState(),
              ApiFailure(:final problem) =>
                OmiErrorState(message: ChatAppsProblem.fromApi(problem).message(context), onRetry: _load),
              ApiSuccess(:final data) when data.isEmpty =>
                OmiEmptyState(icon: Icons.chat_bubble_outline_rounded, title: l10n.chatAppsNoMessages),
              ApiSuccess(:final data) => ListView.separated(
                  // Newest first from the server; read top to bottom like the chat app.
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xxl),
                  itemCount: data.length,
                  separatorBuilder: (_, __) => const SizedBox(height: OmiSpacing.md),
                  itemBuilder: (context, index) {
                    final message = data[data.length - 1 - index];
                    return message.sender == MessageSender.human
                        ? HumanMessage(message: message)
                        : getMarkdownWidget(context, message.text);
                  },
                ),
            },
          ),
        ],
      ),
    );
  }
}
