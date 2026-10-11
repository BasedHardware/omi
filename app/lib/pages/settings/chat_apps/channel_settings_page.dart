import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/pages/settings/chat_apps/channel_chats_page.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_problem.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/chat_apps_analytics.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Manage one chat-app link: show its chats in the Omi app, voice notes, private memories, and disconnect.
///
/// Insights are stored but not applied yet, so that row stays disabled.
class ChannelSettingsPage extends StatelessWidget {
  const ChannelSettingsPage({super.key, required this.linkId});

  final String linkId;

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<MessagingChannelsProvider>();
    final link = provider.linkById(linkId);
    final l10n = context.l10n;
    final channel = link?.channel;
    final name = channel?.displayName ?? link?.channelId ?? '';

    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(name)),
      body: link == null || channel == null
          ? OmiEmptyState(
              icon: Icons.link_off_rounded,
              title: l10n.chatAppsNotConnectedTitle,
              message: l10n.chatAppsNotConnectedMessage,
            )
          : ListView(
              padding: const EdgeInsets.fromLTRB(
                OmiSpacing.md,
                OmiSpacing.sm,
                OmiSpacing.md,
                OmiSpacing.xxl,
              ),
              children: [
                _Header(link: link, channel: channel),
                const SizedBox(height: OmiSpacing.xl),
                OmiSettingsGroup(
                  header: l10n.chatAppsInChannel(name),
                  footer: l10n.chatAppsChannelFooter(name),
                  children: [
                    OmiSettingsRow.toggle(
                      key: const ValueKey('chat_apps_show_in_app'),
                      title: l10n.chatAppsShowInApp,
                      subtitle: link.visibleInApp ? l10n.chatAppsShowInAppOn : l10n.chatAppsShowInAppOff(name),
                      value: link.visibleInApp,
                      onChanged: (value) => _setVisible(context, link, value),
                    ),
                    if (link.visibleInApp)
                      OmiSettingsRow(
                        key: const ValueKey('chat_apps_view_chats'),
                        leading: const Icon(Icons.forum_outlined),
                        title: l10n.chatAppsViewChats,
                        onTap: () => routeToPage(
                          context,
                          ChannelChatsPage(linkId: link.id),
                        ),
                      ),
                    OmiSettingsRow.toggle(
                      key: const ValueKey('chat_apps_voice_notes'),
                      title: l10n.chatAppsVoiceNotes,
                      subtitle: l10n.chatAppsVoiceNotesSubtitle,
                      value: link.voiceNotes,
                      onChanged: (value) => _setVoiceNotes(context, link, value),
                    ),
                    OmiSettingsRow.toggle(
                      key: const ValueKey('chat_apps_private_memories'),
                      title: l10n.chatAppsPrivateMemories,
                      subtitle: l10n.chatAppsPrivateMemoriesSubtitle,
                      value: link.keepPrivateMemoriesInApp,
                      onChanged: (value) => _setPrivateMemories(context, link, value),
                    ),
                    _ComingRow(
                      title: l10n.chatAppsInsights,
                      subtitle: l10n.chatAppsInsightsSubtitle,
                    ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.xl),
                OmiSettingsGroup(
                  footer: l10n.chatAppsDisconnectFooter(name),
                  children: [
                    OmiSettingsRow(
                      key: const ValueKey('chat_apps_disconnect'),
                      title: l10n.chatAppsDisconnectChannel(name),
                      isDestructive: true,
                      showChevron: false,
                      onTap: () => _disconnect(context, link, channel),
                    ),
                  ],
                ),
              ],
            ),
    );
  }

  Future<void> _setVisible(
    BuildContext context,
    ChannelLink link,
    bool visible,
  ) =>
      _apply(
        context,
        context.read<MessagingChannelsProvider>().setVisibleInApp(link, visible),
      );

  Future<void> _setVoiceNotes(
    BuildContext context,
    ChannelLink link,
    bool enabled,
  ) =>
      _apply(
        context,
        context.read<MessagingChannelsProvider>().setVoiceNotes(link, enabled),
      );

  Future<void> _setPrivateMemories(
    BuildContext context,
    ChannelLink link,
    bool enabled,
  ) =>
      _apply(
        context,
        context.read<MessagingChannelsProvider>().setKeepPrivateMemoriesInApp(
              link,
              enabled,
            ),
      );

  Future<void> _apply(
    BuildContext context,
    Future<ApiResult<void>> resultFuture,
  ) async {
    final result = await resultFuture;
    if (!context.mounted) return;
    if (result case ApiFailure(:final problem)) {
      OmiFeedback.error(
        context,
        ChatAppsProblem.fromApi(problem).message(context),
      );
    }
  }

  Future<void> _disconnect(
    BuildContext context,
    ChannelLink link,
    ChatChannel channel,
  ) async {
    final l10n = context.l10n;
    final name = channel.displayName;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.chatAppsDisconnectTitle(name),
      message: l10n.chatAppsDisconnectMessage(name),
      confirmLabel: l10n.disconnect,
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    final result = await context.read<MessagingChannelsProvider>().unlink(link);
    if (!context.mounted) return;
    switch (result) {
      case ApiSuccess():
        ChatAppsAnalytics.disconnected(channel);
        OmiFeedback.confirm(context, l10n.disconnectedFrom(name));
        Navigator.of(context).maybePop();
      case ApiFailure(:final problem):
        OmiFeedback.error(
          context,
          ChatAppsProblem.fromApi(problem).message(context),
        );
    }
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.link, required this.channel});

  final ChannelLink link;
  final ChatChannel channel;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
      ),
      child: Row(
        children: [
          ChatAppLogo(channel, size: 48),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  link.handle ?? channel.displayName,
                  style: OmiType.headline,
                ),
                const SizedBox(height: 2),
                Text(
                  l10n.chatAppsConnectedOn(
                    OmiDateFormat.of(context).date(link.linkedAt),
                  ),
                  style: OmiType.footnote.copyWith(
                    color: OmiColors.textTertiary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A setting the server cannot store yet: a disabled row that says so.
class _ComingRow extends StatelessWidget {
  const _ComingRow({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      enabled: false,
      child: OmiSettingsRow(
        title: title,
        subtitle: subtitle,
        value: context.l10n.chatAppsComingLater,
      ),
    );
  }
}
