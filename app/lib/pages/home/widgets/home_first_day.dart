import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/devices/add_device_page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/pages/home/widgets/home_sections.dart';
import 'package:omi/pages/home/widgets/idle_capture_card.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Home's title on the first day (v2 `FirstDay`): "Welcome, Alex" and "Your first day with Omi",
/// where later days say "Good afternoon".
class HomeFirstDayHeader extends StatelessWidget {
  const HomeFirstDayHeader({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final name = SharedPreferencesUtil().givenName.trim();
    return Padding(
      padding:
          const EdgeInsets.fromLTRB(OmiSize.screenMargin + OmiSpacing.xxs, OmiSpacing.xxs, OmiSize.screenMargin, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            header: true,
            child: Text(
              name.isEmpty ? l10n.homeWelcome : l10n.homeWelcomeName(name),
              style: OmiType.largeTitle,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(height: 2),
          Text(l10n.homeFirstDaySubtitle, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        ],
      ),
    );
  }
}

/// While Omi records the first conversation (v2 `FirstDay` hero): the orb lit on a recessed panel,
/// "Omi is listening", and where the conversation will turn up. A tap opens Live (its controls
/// are there); a Transcribe Later session has no live view, so it only informs.
class FirstDayListeningHero extends StatelessWidget {
  const FirstDayListeningHero({super.key});

  @override
  Widget build(BuildContext context) {
    final capturing = context.select<CaptureProvider, bool>(IdleCaptureCard.isCapturing);
    if (!capturing) return const SizedBox.shrink();
    final l10n = context.l10n;
    final capture = context.read<CaptureProvider>();
    final batch =
        capture.isPhoneMicBatchRecording || (SharedPreferencesUtil().batchModeEnabled && capture.havingRecordingDevice);
    final hero = Container(
      key: const ValueKey('first_day_listening_hero'),
      height: 290,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(color: OmiColors.well, borderRadius: OmiRadius.cardLargeAll),
      child: Stack(
        children: [
          const Positioned(top: 64, left: 0, right: 0, child: Center(child: OmiOrb(size: 112, live: true))),
          Positioned(
            left: 20,
            right: 20,
            bottom: 20,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l10n.homeListeningHeroTitle, style: OmiType.title3.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text(l10n.homeListeningHeroBody, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
        ],
      ),
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.sm),
      child: batch
          ? hero
          : Semantics(
              button: true,
              hint: l10n.liveTranscript,
              child: OmiPressable(
                onTap: () =>
                    routeToPage(context, ConversationCapturingPage(topConversationId: capture.topConversationId)),
                child: hero,
              ),
            ),
    );
  }
}

/// The first days' checklist (v2 `FirstDay` "Getting started · 2 of 4"): connect a device, teach
/// Omi your voice, have a conversation, ask Omi about it. Each step ticks itself off from the
/// app's own state; the card folds away once all four are done.
class HomeGettingStarted extends StatelessWidget {
  const HomeGettingStarted({super.key, required this.conversationCount});

  final int conversationCount;

  void _haveAConversation(BuildContext context) {
    final capture = context.read<CaptureProvider>();
    if (IdleCaptureCard.isCapturing(capture)) {
      routeToPage(context, ConversationCapturingPage(topConversationId: capture.topConversationId));
    } else {
      PhoneCapture.start(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final connected = context.select<DeviceProvider, bool>((d) => (d.pairedDevice?.id ?? '').isNotEmpty);
    final voice = context.select<HomeProvider, bool>((h) => h.hasSpeakerProfile);
    final asked = context
        .select<MessageProvider, bool>((m) => m.messages.any((message) => message.sender == MessageSender.human));
    final steps = [
      (
        id: 'connect',
        title: l10n.gettingStartedConnect,
        done: connected,
        onTap: () => routeToPage(context, const AddDevicePage()),
      ),
      (id: 'voice', title: l10n.teachOmiYourVoice, done: voice, onTap: () => openVoiceProfile(context)),
      (
        id: 'conversation',
        title: l10n.gettingStartedConversation,
        done: conversationCount > 0,
        onTap: () => _haveAConversation(context),
      ),
      (
        id: 'ask',
        title: l10n.gettingStartedAsk,
        done: asked,
        onTap: () => routeToPage(context, const ChatPage(isPivotBottom: false)),
      ),
    ];
    final done = steps.where((step) => step.done).length;
    if (done == steps.length) return const SizedBox.shrink();
    return Padding(
      key: const ValueKey('home_getting_started'),
      padding: const EdgeInsets.only(top: 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, 0, OmiSpacing.xxs, 10),
            child: Row(
              children: [
                Expanded(child: Semantics(header: true, child: Text(l10n.homeGettingStarted, style: OmiType.title3))),
                Text(
                  l10n.homeGettingStartedProgress(done, steps.length),
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                ),
              ],
            ),
          ),
          OmiCard(
            clip: true,
            child: Material(
              type: MaterialType.transparency,
              child: Column(
                children: [
                  for (final (i, step) in steps.indexed) ...[
                    if (i > 0) Divider(height: 0.5, thickness: 0.5, indent: 52, color: OmiColors.border),
                    _StepRow(
                      key: ValueKey('getting_started_${step.id}'),
                      title: step.title,
                      done: step.done,
                      onTap: step.onTap,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({super.key, required this.title, required this.done, required this.onTap});

  final String title;
  final bool done;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: Semantics(
        checked: done,
        button: !done,
        child: InkWell(
          onTap: done
              ? null
              : () {
                  OmiHaptics.selection();
                  onTap();
                },
          splashFactory: NoSplash.splashFactory,
          highlightColor: OmiColors.cellPressed,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: OmiSize.rowMinHeight),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 10),
              child: Row(
                children: [
                  Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: done ? OmiColors.textPrimary : null,
                      border: done ? null : Border.all(color: OmiColors.textTertiary, width: 1.5),
                    ),
                    child: done ? Icon(Icons.check_rounded, size: 16, color: OmiColors.surface0) : null,
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Text(
                      title,
                      style: OmiType.body.copyWith(
                        color: done ? OmiColors.textTertiary : OmiColors.textPrimary,
                        decoration: done ? TextDecoration.lineThrough : null,
                        decorationColor: OmiColors.textTertiary,
                      ),
                    ),
                  ),
                  if (!done) OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// "Good to know" on the first day (v2 `FirstDay`): three tips side by side, scrolling sideways.
class HomeGoodToKnow extends StatelessWidget {
  const HomeGoodToKnow({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final tips = [
      (icon: Icons.back_hand_outlined, title: l10n.tipFinishTitle, body: l10n.tipFinishBody),
      (icon: Icons.star_border_rounded, title: l10n.tipStarTitle, body: l10n.tipStarBody),
      (icon: Icons.lock_outline_rounded, title: l10n.tipPrivateTitle, body: l10n.tipPrivateBody),
    ];
    return Padding(
      key: const ValueKey('home_good_to_know'),
      padding: const EdgeInsets.only(top: 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSize.screenMargin),
            child: HomeSectionHeader(title: l10n.homeGoodToKnow),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: OmiSize.screenMargin),
            child: IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final (i, tip) in tips.indexed) ...[
                    if (i > 0) const SizedBox(width: OmiSpacing.sm),
                    _TipCard(icon: tip.icon, title: tip.title, body: tip.body),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TipCard extends StatelessWidget {
  const _TipCard({required this.icon, required this.title, required this.body});

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: Container(
        width: 240,
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ExcludeSemantics(child: Icon(icon, size: 20, color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.xs),
            Text(title, style: OmiType.headline),
            const SizedBox(height: 4),
            Text(body, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ],
        ),
      ),
    );
  }
}
