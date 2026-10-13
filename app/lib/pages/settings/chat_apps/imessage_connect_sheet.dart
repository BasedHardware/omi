import 'dart:async';

import 'package:flutter/material.dart';

import 'package:flutter_contacts/flutter_contacts.dart';
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

/// Connect iMessage: the person texts Omi a one-time code from the number to link. Messages opens
/// prefilled; the sheet then waits for the backend to see the text. Resolves to the new link, or
/// null when closed first.
Future<ChannelLink?> showIMessageConnectSheet(BuildContext context) {
  return showOmiSheet<ChannelLink>(
    context: context,
    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
    builder: (_) => const IMessageConnectSheet(),
  );
}

/// Test seam: opens the system "new contact" form.
@visibleForTesting
Future<void> Function(String name, String number) addContactLauncher = _addContact;

Future<void> _addContact(String name, String number) async {
  await FlutterContacts.native.showCreator(
    contact: Contact(
      name: Name(first: name),
      phones: [Phone(number: number)],
    ),
  );
}

const _messagesBlue = Color(0xFF0A84FF); // omi-ux-allow: color-literal -- the Messages bubble, a brand colour
const _onMessagesBlue = Color(0xFFFFFFFF); // omi-ux-allow: color-literal -- text on the Messages bubble

class IMessageConnectSheet extends StatefulWidget {
  const IMessageConnectSheet({super.key});

  @override
  State<IMessageConnectSheet> createState() => _IMessageConnectSheetState();
}

class _IMessageConnectSheetState extends State<IMessageConnectSheet>
    with WidgetsBindingObserver, ChannelLinkWaiter<IMessageConnectSheet> {
  wire.GeneratedChannelLinkProof? _proof;
  ChatAppsProblem? _problem;
  bool _minting = false;

  /// Messages has been opened once; the sheet shows the waiting step.
  bool _sent = false;
  Timer? _clock;

  @override
  ChatChannel get waitChannel => ChatChannel.imessage;

  ChatChannelEndpoint? get _endpoint => context.read<MessagingChannelsProvider>().config.endpoint(ChatChannel.imessage);

  String? _address(wire.GeneratedChannelLinkProof? proof) {
    final fromApi = proof?.address?.trim();
    if (fromApi != null && fromApi.isNotEmpty) return fromApi;
    return _endpoint?.address;
  }

  bool get _expired => _proof != null && !_proof!.expiresAt.isAfter(DateTime.now());

  String _body(String code) => context.l10n.chatAppsIMessageBody(code);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _mint());
  }

  @override
  void dispose() {
    _clock?.cancel();
    super.dispose();
  }

  @override
  void onLinked(ChannelLink link) {
    ChatAppsAnalytics.connected(ChatChannel.imessage);
    Navigator.of(context).pop(link);
  }

  Future<void> _mint() async {
    if (_endpoint == null) {
      setState(() => _problem = ChatAppsProblem.unavailable);
      return;
    }
    setState(() {
      _minting = true;
      _problem = null;
    });
    final result = await context.read<MessagingChannelsProvider>().mintProof(
          ChatChannel.imessage,
          kind: 'code',
        );
    if (!mounted) return;
    setState(() {
      _minting = false;
      switch (result) {
        case ApiSuccess(:final data):
          _proof = data;
          _sent = false;
        case ApiFailure(:final problem):
          _problem = ChatAppsProblem.fromApi(problem);
      }
    });
    _clock?.cancel();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {});
      if (_expired) _clock?.cancel();
    });
  }

  Future<void> _openMessages() async {
    final endpoint = _endpoint;
    final proof = _proof;
    if (endpoint == null || proof == null) return;
    if (!_sent) ChatAppsAnalytics.connectStarted(ChatChannel.imessage);
    final opened = await openChatAppProof(
      ChatChannel.imessage,
      endpoint,
      deepLink: proof.deepLink,
      address: proof.address,
      body: _body(proof.proof),
    );
    if (!mounted) return;
    if (!opened) {
      OmiFeedback.error(
        context,
        context.l10n.chatAppsCouldNotOpen(context.l10n.chatAppsMessagesApp),
      );
    }
    // Waiting starts either way: the code can also be sent by hand.
    setState(() => _sent = true);
    startWaiting(until: proof.expiresAt);
  }

  Future<void> _addToContacts() async {
    final endpoint = _endpoint;
    if (endpoint == null) return;
    try {
      await addContactLauncher('Omi', _address(_proof) ?? endpoint.address);
    } catch (_) {
      if (mounted)
        OmiFeedback.error(
          context,
          context.l10n.chatAppsCouldNotOpen(context.l10n.chatAppsContactsApp),
        );
    }
  }

  Future<void> _getNewCode() async {
    stopWaiting();
    await _mint();
  }

  @override
  Widget build(BuildContext context) {
    final body = _sent && _proof != null ? _buildWaiting(context, _proof!) : _buildCompose(context);
    return SingleChildScrollView(child: body);
  }

  Widget _buildCompose(BuildContext context) {
    final l10n = context.l10n;
    final endpoint = _endpoint;
    final proof = _proof;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Center(child: ChatAppLogo(ChatChannel.imessage, size: 56)),
        const SizedBox(height: OmiSpacing.md),
        ChatAppsSheetHeading(
          title: l10n.chatAppsConnectIMessageTitle,
          message: l10n.chatAppsConnectIMessageMessage,
        ),
        const SizedBox(height: OmiSpacing.lg),
        Container(
          padding: const EdgeInsets.all(OmiSpacing.md),
          decoration: BoxDecoration(
            color: OmiColors.surface0,
            border: Border.all(color: OmiColors.border),
            borderRadius: OmiRadius.lgAll,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      l10n.chatAppsIMessageTo(_address(proof) ?? ''),
                      style: OmiType.footnote.copyWith(
                        color: OmiColors.textTertiary,
                      ),
                    ),
                  ),
                  Text(
                    l10n.chatAppsPrefilled,
                    style: OmiType.footnote.copyWith(
                      color: OmiColors.textTertiary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: OmiSpacing.sm),
              Align(
                alignment: Alignment.centerRight,
                child: proof == null
                    ? (_minting
                        ? const Padding(
                            padding: EdgeInsets.all(OmiSpacing.xs),
                            child: OmiSpinner(size: OmiSpinnerSize.small),
                          )
                        : const SizedBox(height: 40))
                    : Container(
                        key: const ValueKey('chat_apps_imessage_bubble'),
                        padding: const EdgeInsets.symmetric(
                          horizontal: OmiSpacing.sm + 2,
                          vertical: OmiSpacing.sm - 2,
                        ),
                        decoration: const BoxDecoration(
                          color: _messagesBlue,
                          borderRadius: BorderRadius.all(Radius.circular(18)),
                        ),
                        child: Text(
                          _body(proof.proof),
                          style: OmiType.callout.copyWith(
                            color: _onMessagesBlue,
                          ),
                        ),
                      ),
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.md + 2),
        ChatAppsBullet(
          icon: Icons.info_outline_rounded,
          text: l10n.chatAppsCodeNote,
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
        ),
        const SizedBox(height: OmiSpacing.sm - 2),
        ChatAppsBullet(
          icon: Icons.info_outline_rounded,
          text: l10n.chatAppsRepliesOnlyNote,
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
        ),
        if (_problem != null) ...[
          const SizedBox(height: OmiSpacing.md),
          ChatAppsProblemLine(_problem!),
        ],
        const SizedBox(height: OmiSpacing.lg),
        if (_problem != null && !_problem!.blocksRetry)
          OmiButton(label: l10n.tryAgain, expand: true, onPressed: _mint)
        else
          OmiButton(
            key: const ValueKey('chat_apps_open_messages'),
            label: l10n.chatAppsOpenMessages,
            expand: true,
            isLoading: _minting,
            onPressed: proof == null || _expired ? null : _openMessages,
          ),
        const SizedBox(height: OmiSpacing.xxs),
        OmiButton.tertiary(
          key: const ValueKey('chat_apps_add_contact'),
          label: l10n.chatAppsAddToContacts,
          expand: true,
          onPressed: endpoint == null ? null : _addToContacts,
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
    );
  }

  Widget _buildWaiting(
    BuildContext context,
    wire.GeneratedChannelLinkProof proof,
  ) {
    final l10n = context.l10n;
    final remaining = proof.expiresAt.difference(DateTime.now());
    final expired = remaining <= Duration.zero;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: OmiSpacing.lg),
        Center(
          child: expired
              ? ExcludeSemantics(
                  child: Icon(
                    Icons.timer_off_outlined,
                    size: 40,
                    color: OmiColors.textTertiary,
                  ),
                )
              : const OmiSpinner(size: OmiSpinnerSize.large),
        ),
        const SizedBox(height: OmiSpacing.xl),
        ChatAppsSheetHeading(
          title: expired ? l10n.chatAppsCodeExpiredTitle : l10n.chatAppsWaitingTitle,
          message: expired ? l10n.chatAppsCodeExpiredMessage : l10n.chatAppsWaitingMessage,
        ),
        const SizedBox(height: OmiSpacing.xl),
        if (!expired)
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: OmiSpacing.md,
              vertical: OmiSpacing.sm + 2,
            ),
            decoration: BoxDecoration(
              color: OmiColors.surface0,
              border: Border.all(color: OmiColors.border),
              borderRadius: OmiRadius.lgAll,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  l10n.chatAppsTextThisTo(_address(proof) ?? ''),
                  style: OmiType.footnote.copyWith(
                    color: OmiColors.textTertiary,
                  ),
                ),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        groupedLinkCode(proof.proof),
                        key: const ValueKey('chat_apps_link_code'),
                        style: OmiType.headline.copyWith(
                          letterSpacing: 1.5,
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                    ),
                    const SizedBox(width: OmiSpacing.xs),
                    OmiButton.secondary(
                      key: const ValueKey('chat_apps_copy_code'),
                      label: l10n.copy,
                      size: OmiButtonSize.compact,
                      onPressed: () => OmiClipboard.copy(
                        context,
                        _body(proof.proof),
                        what: l10n.chatAppsMessage,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        if (!expired) ...[
          const SizedBox(height: OmiSpacing.md),
          Semantics(
            liveRegion: false,
            child: Text(
              l10n.chatAppsCodeExpiresIn(
                OmiDuration.offset(remaining.inSeconds),
              ),
              key: const ValueKey('chat_apps_code_countdown'),
              textAlign: TextAlign.center,
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            ),
          ),
        ],
        if (_problem != null) ...[
          const SizedBox(height: OmiSpacing.md),
          ChatAppsProblemLine(_problem!),
        ],
        const SizedBox(height: OmiSpacing.lg),
        if (expired)
          OmiButton(
            key: const ValueKey('chat_apps_new_code'),
            label: l10n.chatAppsGetNewCode,
            expand: true,
            isLoading: _minting,
            onPressed: _getNewCode,
          )
        else
          OmiButton.secondary(
            key: const ValueKey('chat_apps_open_messages_again'),
            label: l10n.chatAppsOpenMessagesAgain,
            expand: true,
            onPressed: _openMessages,
          ),
        const SizedBox(height: OmiSpacing.xxs),
        OmiButton.tertiary(
          key: const ValueKey('chat_apps_cancel_imessage'),
          label: l10n.cancel,
          expand: true,
          onPressed: () => Navigator.of(context).pop(),
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
    );
  }
}
