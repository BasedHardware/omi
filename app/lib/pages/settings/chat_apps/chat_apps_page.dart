import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/chat_apps/channel_settings_page.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/imessage_connect_sheet.dart';
import 'package:omi/pages/settings/chat_apps/telegram_connect_sheet.dart';
import 'package:omi/pages/settings/chat_apps/whatsapp_waitlist_sheet.dart';
import 'package:omi/pages/settings/integration_selection_card.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// "Chat apps" on Integrations: one row opening [ChatAppsPage]. Hidden unless the surface is on
/// for this account or a link already exists (so Disconnect stays reachable).
class ChatAppsIntegrationsEntry extends StatelessWidget {
  const ChatAppsIntegrationsEntry({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<MessagingChannelsProvider>();
    if (!provider.showEntry) return const SizedBox.shrink();
    final l10n = context.l10n;
    return Padding(
      key: const ValueKey('chat_apps_integrations_entry'),
      padding: const EdgeInsets.only(top: OmiSpacing.sm, bottom: OmiSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          OmiSectionHeader(
            l10n.chatAppsChannelsTitle,
            subtitle: l10n.chatAppsEntrySubtitle,
            trailing: SettingsTag(l10n.newTag, OmiColors.success),
          ),
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const ValueKey('chat_apps_open'),
                leading: const StackedChatAppLogos(),
                title: l10n.chatAppsEntryTitle,
                subtitle: l10n.chatAppsEntryRowSubtitle,
                onTap: () => routeToPage(context, const ChatAppsPage()),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Whether the account holds the plan the gateway admits. Unknown until the subscription loads.
enum _ProStatus { unknown, pro, free }

/// Connect Telegram and iMessage, see what is connected, and join the WhatsApp waitlist.
class ChatAppsPage extends StatefulWidget {
  const ChatAppsPage({super.key});

  @override
  State<ChatAppsPage> createState() => _ChatAppsPageState();
}

class _ChatAppsPageState extends State<ChatAppsPage> {
  /// Set when a connect sheet just finished, for the success banner and the open button.
  ChatChannel? _justConnected;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(context.read<MessagingChannelsProvider>().load());
      unawaited(context.read<UsageProvider>().fetchSubscription());
    });
  }

  _ProStatus _proStatus(UsageProvider usage) {
    final plan = usage.subscription?.subscription.plan;
    if (plan == null) return _ProStatus.unknown;
    return plan.isPaid ? _ProStatus.pro : _ProStatus.free;
  }

  void _openPlans() {
    if (!context.read<UsageProvider>().showSubscriptionUI) return;
    PlatformManager.instance.analytics.paywallOpened('Chat Apps');
    routeToPage(context, const UsagePage(showUpgradeDialog: true));
  }

  Future<void> _connect(ChatChannel channel) async {
    final sheet = switch (channel) {
      ChatChannel.telegram => showTelegramConnectSheet(context),
      ChatChannel.imessage => showIMessageConnectSheet(context),
      ChatChannel.whatsapp => Future<ChannelLink?>.value(),
    };
    final link = await sheet;
    if (link != null && mounted) setState(() => _justConnected = channel);
  }

  Future<void> _openWaitlist(MessagingChannelsProvider provider) async {
    final offerTelegram = provider.linkFor(ChatChannel.telegram) == null &&
        provider.config.endpoint(ChatChannel.telegram) != null &&
        _proStatus(context.read<UsageProvider>()) != _ProStatus.free;
    final action = await showWhatsAppWaitlistSheet(context, offerTelegram: offerTelegram);
    if (action == WhatsAppWaitlistAction.useTelegram && mounted) await _connect(ChatChannel.telegram);
  }

  Future<void> _openChannel(ChatChannel channel) async {
    final endpoint = context.read<MessagingChannelsProvider>().config.endpoint(channel);
    final opened = endpoint != null && await openChatApp(channel, endpoint);
    if (opened || !mounted) return;
    final l10n = context.l10n;
    OmiFeedback.error(context,
        l10n.chatAppsCouldNotOpen(channel == ChatChannel.imessage ? l10n.chatAppsMessagesApp : channel.displayName));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<MessagingChannelsProvider>();
    final pro = _proStatus(context.watch<UsageProvider>());
    final online = context.watch<ConnectivityProvider>().isConnected;
    final justConnected = _justConnected;
    final anyConnected = [ChatChannel.telegram, ChatChannel.imessage].any((c) => provider.linkFor(c) != null);

    final Widget body;
    if (!provider.linksLoaded && provider.linksProblem == null) {
      body = const OmiLoadingState();
    } else if (!provider.linksLoaded) {
      body = OmiErrorState(
        title: l10n.chatAppsLoadFailedTitle,
        message: online ? l10n.chatAppsProblemFailed : l10n.chatAppsProblemOffline,
        onRetry: provider.refreshLinks,
      );
    } else {
      body = RefreshIndicator(
        onRefresh: provider.refreshLinks,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xxl),
          children: [
            if (justConnected != null) ...[
              _ConnectedBanner(channel: justConnected),
              const SizedBox(height: OmiSpacing.lg),
            ] else ...[
              const _Hero(),
              const SizedBox(height: OmiSpacing.lg),
            ],
            if (!online) ...[
              _InlineNotice(icon: Icons.wifi_off_rounded, text: l10n.chatAppsProblemOffline),
              const SizedBox(height: OmiSpacing.sm),
            ] else if (provider.linksProblem != null) ...[
              _InlineNotice(icon: Icons.error_outline_rounded, text: l10n.chatAppsRefreshFailed),
              const SizedBox(height: OmiSpacing.sm),
            ],
            OmiSettingsGroup(
              footer: l10n.chatAppsMoreComing,
              children: [
                for (final channel in ChatChannel.values) _channelRow(context, provider, channel, pro),
              ],
            ),
            const SizedBox(height: OmiSpacing.xl),
            if (pro == _ProStatus.free)
              _ProCard(onUpgrade: _openPlans)
            else if (anyConnected)
              const _TryAsking()
            else
              const _WhatOmiDoes(),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.chatAppsChannelsTitle)),
      body: SafeArea(top: false, child: body),
      bottomNavigationBar: justConnected == null
          ? null
          : SafeArea(
              minimum: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
              child: OmiButton(
                key: const ValueKey('chat_apps_open_connected'),
                label: justConnected == ChatChannel.imessage
                    ? l10n.chatAppsOpenMessages
                    : l10n.chatAppsOpenApp(justConnected.displayName),
                expand: true,
                onPressed: () => _openChannel(justConnected),
              ),
            ),
    );
  }

  Widget _channelRow(BuildContext context, MessagingChannelsProvider provider, ChatChannel channel, _ProStatus pro) {
    final l10n = context.l10n;
    final link = provider.linkFor(channel);
    final key = ValueKey('chat_apps_row_${channel.wireId}');
    final logo = ChatAppLogo(channel);

    if (link != null) {
      final handle = link.handle;
      return OmiSettingsRow(
        key: key,
        leading: logo,
        title: channel.displayName,
        subtitle: handle == null ? l10n.connected : l10n.chatAppsConnectedAs(handle),
        trailing: const ChatAppsConnectedChip(),
        showChevron: true,
        onTap: () => routeToPage(context, ChannelSettingsPage(linkId: link.id)),
      );
    }
    if (channel == ChatChannel.whatsapp) {
      final joined = provider.whatsAppWaitlisted;
      return OmiSettingsRow(
        key: key,
        leading: logo,
        title: channel.displayName,
        subtitle: l10n.chatAppsNotAvailableYet,
        trailing: IntegrationStatusChip(joined ? l10n.chatAppsOnTheList : l10n.chatAppsNotifyMe,
            tone: IntegrationChipTone.muted),
        onTap: () => _openWaitlist(provider),
      );
    }
    final endpoint = provider.config.endpoint(channel);
    final subtitle = channel == ChatChannel.telegram ? l10n.chatAppsTelegramSubtitle : l10n.chatAppsIMessageSubtitle;
    if (endpoint == null) {
      return OmiSettingsRow(
        key: key,
        leading: logo,
        title: channel.displayName,
        subtitle: l10n.chatAppsNotAvailableYet,
        trailing: IntegrationStatusChip(l10n.comingSoon, tone: IntegrationChipTone.muted),
      );
    }
    if (pro == _ProStatus.free) {
      return Opacity(
        opacity: 0.55,
        child: OmiSettingsRow(
          key: key,
          leading: logo,
          title: channel.displayName,
          subtitle: subtitle,
          trailing: Semantics(
            label: l10n.chatAppsLocked,
            child: Icon(Icons.lock_outline_rounded, size: 18, color: OmiColors.textSecondary),
          ),
          onTap: _openPlans,
        ),
      );
    }
    return OmiSettingsRow(
      key: key,
      leading: logo,
      title: channel.displayName,
      subtitle: subtitle,
      trailing: IntegrationStatusChip(l10n.connect),
      onTap: () => _connect(channel),
    );
  }
}

class _Hero extends StatelessWidget {
  const _Hero();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const OmiRingMark(),
              const SizedBox(width: OmiSpacing.xs),
              ChatAppsOutlineTag(l10n.chatAppsIncludedWithPro),
            ],
          ),
          const SizedBox(height: OmiSpacing.sm),
          Semantics(header: true, child: Text(l10n.chatAppsHeroTitle, style: OmiType.title1)),
          const SizedBox(height: OmiSpacing.sm - 2),
          Text(l10n.chatAppsHeroMessage, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        ],
      ),
    );
  }
}

class _ConnectedBanner extends StatelessWidget {
  const _ConnectedBanner({required this.channel});

  final ChatChannel channel;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final app = channel == ChatChannel.imessage ? l10n.chatAppsMessagesApp : channel.displayName;
    return Semantics(
      liveRegion: true,
      child: Container(
        key: const ValueKey('chat_apps_connected_banner'),
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm + 2),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(color: OmiColors.success, shape: BoxShape.circle),
              child: ExcludeSemantics(child: Icon(Icons.check_rounded, size: 20, color: OmiColors.surface0)),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.chatAppsIsConnected(channel.displayName),
                      style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(l10n.chatAppsReplyThereAnytime(app),
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
        child: Row(
          children: [
            ExcludeSemantics(child: Icon(icon, size: 16, color: OmiColors.textTertiary)),
            const SizedBox(width: OmiSpacing.xs),
            Expanded(child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary))),
          ],
        ),
      ),
    );
  }
}

class _WhatOmiDoes extends StatelessWidget {
  const _WhatOmiDoes();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final check = OmiColors.success;
    return Container(
      key: const ValueKey('chat_apps_what_omi_does'),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(border: Border.all(color: OmiColors.border), borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            header: true,
            child: Text(l10n.chatAppsWhatOmiDoes, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
          ),
          const SizedBox(height: OmiSpacing.sm),
          ChatAppsBullet(icon: Icons.check_rounded, iconColor: check, text: l10n.chatAppsDoesAnswer),
          const SizedBox(height: OmiSpacing.sm),
          ChatAppsBullet(icon: Icons.check_rounded, iconColor: check, text: l10n.chatAppsDoesSave),
          const SizedBox(height: OmiSpacing.sm),
          ChatAppsBullet(icon: Icons.check_rounded, iconColor: check, text: l10n.chatAppsDoesFiles),
          const SizedBox(height: OmiSpacing.sm),
          ChatAppsBullet(icon: Icons.close_rounded, text: l10n.chatAppsNeverMessagesOthers),
        ],
      ),
    );
  }
}

class _TryAsking extends StatelessWidget {
  const _TryAsking();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      key: const ValueKey('chat_apps_try_asking'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSectionHeader(l10n.chatAppsTryAsking),
        for (final prompt in [l10n.chatAppsTryPromise, l10n.chatAppsTryWeek, l10n.chatAppsTryRemind]) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm + 2, vertical: OmiSpacing.sm),
            decoration: BoxDecoration(border: Border.all(color: OmiColors.border), borderRadius: OmiRadius.mdAll),
            child: Text(prompt, style: OmiType.subhead),
          ),
          const SizedBox(height: OmiSpacing.xs),
        ],
      ],
    );
  }
}

class _ProCard extends StatelessWidget {
  const _ProCard({required this.onUpgrade});

  final VoidCallback onUpgrade;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final check = OmiColors.success;
    return Container(
      key: const ValueKey('chat_apps_pro_card'),
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: BoxDecoration(border: Border.all(color: OmiColors.border), borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(alignment: Alignment.centerLeft, child: ChatAppsFilledTag(l10n.chatAppsOmiPro)),
          const SizedBox(height: OmiSpacing.sm),
          Semantics(header: true, child: Text(l10n.chatAppsPartOfPro, style: OmiType.title3)),
          const SizedBox(height: OmiSpacing.sm),
          ChatAppsBullet(icon: Icons.check_rounded, iconColor: check, text: l10n.chatAppsProPerkText),
          const SizedBox(height: OmiSpacing.sm),
          ChatAppsBullet(icon: Icons.check_rounded, iconColor: check, text: l10n.chatAppsProPerkSave),
          const SizedBox(height: OmiSpacing.sm),
          ChatAppsBullet(icon: Icons.check_rounded, iconColor: check, text: l10n.chatAppsProPerkContext),
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
              key: const ValueKey('chat_apps_upgrade'), label: l10n.upgradeToPro, expand: true, onPressed: onUpgrade),
        ],
      ),
    );
  }
}
