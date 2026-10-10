import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/messaging_wire.g.dart' as wire;
import 'package:omi/pages/settings/chat_apps/channel_link_waiter.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_problem.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/chat_apps_analytics.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Connect Telegram: mint a one-time token, open `t.me/<bot>?start=<token>`, and wait for the
/// person to tap Start. Resolves to the new link, or null when closed first.
Future<ChannelLink?> showTelegramConnectSheet(BuildContext context) {
  return showOmiSheet<ChannelLink>(
    context: context,
    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
    builder: (_) => const TelegramConnectSheet(),
  );
}

class TelegramConnectSheet extends StatefulWidget {
  const TelegramConnectSheet({super.key});

  @override
  State<TelegramConnectSheet> createState() => _TelegramConnectSheetState();
}

class _TelegramConnectSheetState extends State<TelegramConnectSheet>
    with WidgetsBindingObserver, ChannelLinkWaiter<TelegramConnectSheet> {
  wire.GeneratedChannelLinkProof? _proof;
  ChatAppsProblem? _problem;
  bool _opened = false;

  @override
  ChatChannel get waitChannel => ChatChannel.telegram;

  ChatChannelEndpoint? get _endpoint => context.read<MessagingChannelsProvider>().config.endpoint(ChatChannel.telegram);

  bool get _proofFresh {
    final proof = _proof;
    return proof != null &&
        proof.expiresAt.isAfter(
          DateTime.now().add(const Duration(seconds: 15)),
        );
  }

  @override
  void onLinked(ChannelLink link) {
    ChatAppsAnalytics.connected(ChatChannel.telegram);
    Navigator.of(context).pop(link);
  }

  /// A token that is still good for at least a few seconds, minting a new one if needed.
  Future<wire.GeneratedChannelLinkProof?> _token() async {
    if (_proofFresh) return _proof;
    final result = await context.read<MessagingChannelsProvider>().mintProof(
          ChatChannel.telegram,
          kind: 'token',
        );
    if (!mounted) return null;
    switch (result) {
      case ApiSuccess(:final data):
        setState(() {
          _proof = data;
          _problem = null;
        });
        return data;
      case ApiFailure(:final problem):
        setState(() => _problem = ChatAppsProblem.fromApi(problem));
        return null;
    }
  }

  Future<void> _openTelegram() async {
    final endpoint = _endpoint;
    if (endpoint == null) {
      setState(() => _problem = ChatAppsProblem.unavailable);
      return;
    }
    ChatAppsAnalytics.connectStarted(ChatChannel.telegram);
    final proof = await _token();
    if (proof == null || !mounted) return;
    final opened = await openChatAppProof(
      ChatChannel.telegram,
      endpoint,
      deepLink: proof.deepLink,
      address: proof.address,
      startToken: proof.proof,
    );
    if (!mounted) return;
    if (!opened) {
      OmiFeedback.error(
        context,
        context.l10n.chatAppsCouldNotOpen(ChatChannel.telegram.displayName),
      );
      return;
    }
    setState(() => _opened = true);
    startWaiting(until: proof.expiresAt);
  }

  Future<void> _copyLink() async {
    final endpoint = _endpoint;
    if (endpoint == null) return;
    final proof = await _token();
    if (proof == null || !mounted) return;
    final link = chatAppProofUri(
      channel: ChatChannel.telegram,
      endpoint: endpoint,
      deepLink: proof.deepLink,
      address: proof.address,
      startToken: proof.proof,
      platform: TargetPlatform.iOS,
    );
    if (link == null) return;
    await OmiClipboard.copy(
      context,
      link.toString(),
      what: context.l10n.chatAppsLink,
    );
    if (!mounted) return;
    setState(() => _opened = true);
    startWaiting(until: proof.expiresAt);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final expired = _opened && !isWaitingForLink;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const ChatAppLogo(ChatChannel.telegram, size: 56),
              const SizedBox(width: OmiSpacing.sm),
              ExcludeSemantics(
                child: Icon(
                  Icons.arrow_forward_rounded,
                  size: 20,
                  color: OmiColors.textDisabled,
                ),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Container(
                width: 56,
                height: 56,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: OmiColors.surface0,
                  border: Border.all(color: OmiColors.border),
                  borderRadius: OmiRadius.mdAll,
                ),
                child: const OmiRingMark(),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.lg),
          ChatAppsSheetHeading(
            title: l10n.chatAppsConnectTelegramTitle,
            message: l10n.chatAppsConnectTelegramMessage,
          ),
          const SizedBox(height: OmiSpacing.xl),
          _Step(number: 1, text: l10n.chatAppsTelegramStepOpen),
          const SizedBox(height: OmiSpacing.sm + 2),
          _Step(number: 2, text: l10n.chatAppsTelegramStepStart),
          const SizedBox(height: OmiSpacing.sm + 2),
          _Step(number: 3, text: l10n.chatAppsTelegramStepReturn),
          const SizedBox(height: OmiSpacing.xl),
          ChatAppsNote(
            icon: Icons.lock_outline_rounded,
            message: l10n.chatAppsTelegramPrivacyNote,
          ),
          if (_problem != null) ...[
            const SizedBox(height: OmiSpacing.md),
            ChatAppsProblemLine(_problem!),
          ] else if (isWaitingForLink) ...[
            const SizedBox(height: OmiSpacing.md),
            _WaitingLine(l10n.chatAppsTelegramWaiting),
          ] else if (expired) ...[
            const SizedBox(height: OmiSpacing.md),
            Text(
              l10n.chatAppsLinkExpired,
              key: const ValueKey('chat_apps_telegram_expired'),
              textAlign: TextAlign.center,
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ],
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
            key: const ValueKey('chat_apps_open_telegram'),
            label: l10n.chatAppsOpenApp(ChatChannel.telegram.displayName),
            expand: true,
            onPressed: _problem?.blocksRetry == true ? null : _openTelegram,
          ),
          const SizedBox(height: OmiSpacing.xxs),
          Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                l10n.chatAppsTelegramOtherDevice,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
              ),
              OmiButton.tertiary(
                key: const ValueKey('chat_apps_copy_telegram_link'),
                label: l10n.copyLink,
                size: OmiButtonSize.compact,
                onPressed: _problem?.blocksRetry == true ? null : _copyLink,
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}

class _Step extends StatelessWidget {
  const _Step({required this.number, required this.text});

  final int number;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 28,
          height: 28,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: OmiColors.surface2,
            shape: BoxShape.circle,
          ),
          child: Text(
            '$number',
            style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(child: Text(text, style: OmiType.callout)),
      ],
    );
  }
}

class _WaitingLine extends StatelessWidget {
  const _WaitingLine(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const OmiSpinner(size: OmiSpinnerSize.small),
          const SizedBox(width: OmiSpacing.xs),
          Flexible(
            child: Text(
              text,
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ),
        ],
      ),
    );
  }
}
