// The End action on a v3 conversation in progress; owns only when it shows and what it calls.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/widgets/footer_glass.dart';

/// Ends the conversation this phone is capturing: the same action as a pendant double-tap
/// (`CaptureProvider.forceProcessingCurrentConversation`). It sits in the live conversation's detail
/// bar beside Ask Omi, never on Home.
///
/// An overlapping transcript segment or the verified source recording establishes ownership.
/// A live window on another device must never end this phone's capture.
///
/// One tap ends it. The capture keeps its segments until the WAL drain finishes (seconds), so the
/// button is still on screen meanwhile; taps before that settles are ignored rather than starting a
/// second finalize, as the pendant's double-tap gate does.
class LiveConversationEndButton extends StatefulWidget {
  const LiveConversationEndButton(
      {super.key, required this.conversation, this.leadingGap = 10, this.onEndSuppressionChanged, this.onTray = false});

  /// Experimental design: on the live bar's dark tray End is a flat red pill with a white label.
  final bool onTray;

  final ServerConversation conversation;
  final double leadingGap;
  final ValueChanged<bool>? onEndSuppressionChanged;

  /// True when [conversation] holds any of this phone's captured segments.
  static bool ownsCapture(ServerConversation conversation, Iterable<String> capturedIds) {
    final captured = capturedIds.toSet();
    if (captured.isEmpty) return false;
    return conversation.transcriptSegments.any((segment) => captured.contains(segment.id));
  }

  /// This app install as the server records it on every recording it receives from this phone, over the
  /// listening connection or an upload: the two headers of each request, joined (`{platform}_{hash}`).
  /// Null until start-up has read the hash.
  @visibleForTesting
  static String? Function() ownDeviceId = _platformDeviceId;

  static String? _platformDeviceId() {
    try {
      final hash = PlatformManager.instance.deviceIdHash;
      return hash.isEmpty ? null : '${PlatformManager.instance.platform}_$hash';
    } catch (_) {
      return null;
    }
  }

  /// The server says the latest speech of the account's open conversation ([currentLiveId]) came from
  /// this app install. Read only by reliability experiments (`end_button_by_device`, `instant_live_text`).
  static bool latestSpeechFromThisDevice(ServerConversation conversation,
          {String? currentLiveId, String? liveCaptureDeviceId}) =>
      conversation.id == currentLiveId && liveCaptureDeviceId != null && liveCaptureDeviceId == ownDeviceId();

  /// Reliability experiment `end_button_by_device`: [latestSpeechFromThisDevice] decides End.
  static bool fedByThisDevice(ServerConversation conversation, {String? currentLiveId, String? liveCaptureDeviceId}) =>
      ReliabilityExperiments.enabled('end_button_by_device') &&
      latestSpeechFromThisDevice(conversation, currentLiveId: currentLiveId, liveCaptureDeviceId: liveCaptureDeviceId);

  /// Whether the current capture can finish this window. [liveCaptureDeviceId] is the live read's
  /// device for [currentLiveId], read only by the experiment above.
  static bool phoneCaptures(ServerConversation conversation, CaptureProvider capture,
      {String? currentLiveId, String? liveCaptureDeviceId}) {
    // The device match needs no listening session: uploaded files carry the same device id.
    if (fedByThisDevice(conversation, currentLiveId: currentLiveId, liveCaptureDeviceId: liveCaptureDeviceId)) {
      return true;
    }
    final verified = capture.verifiedLiveServerRecordingId;
    final recordings = conversation.v3?.recordingIds ?? const <String>[];
    if (verified != null && capture.hasClosedServerRecording(verified)) {
      // Process Now can close the recording before Listen announces its replacement.
      // The local close clears segment arrivals. Require a segment received since that
      // cut in the current live window, and reject windows still listing the closed source.
      return EpisodePresentation.streamingSource(capture) != null &&
          conversation.id == currentLiveId &&
          recordings.isNotEmpty &&
          !recordings.contains(verified) &&
          ownsCapture(conversation, capture.locallyReceivedSegmentIds);
    }
    // Listen may rotate while the client capture ID and earlier segments are still
    // present. A window that names its sources must then list the verified recording.
    if (verified != null && recordings.isNotEmpty) return recordings.contains(verified);
    if (EpisodePresentation.streamingSource(capture) == null && verified == null) return false;
    return recordings.contains(capture.activeRecordingId) ||
        ownsCapture(conversation, capture.locallyReceivedSegmentIds);
  }

  @override
  State<LiveConversationEndButton> createState() => _LiveConversationEndButtonState();
}

class _LiveConversationEndButtonState extends State<LiveConversationEndButton> {
  bool _ended = false;
  // Failure count when a successful close latched End; a later unsuccessful settlement releases it.
  int? _latchedFailures;

  @override
  Widget build(BuildContext context) {
    final conversation = widget.conversation;
    final currentLiveId = context.select<ConversationsV3Provider?, String?>((v3) => v3?.live?.id);
    final liveDevice = context.select<ConversationsV3Provider?, String?>((v3) => v3?.live?.v3?.captureDeviceId);
    final mine = context.select<CaptureProvider?, bool>(
      (capture) =>
          capture != null &&
          LiveConversationEndButton.phoneCaptures(conversation, capture,
              currentLiveId: currentLiveId, liveCaptureDeviceId: liveDevice),
    );
    final failures = context.select<ConversationsV3Provider?, int>((v3) => v3?.finishFailures ?? 0);
    if (_ended && _latchedFailures != null && failures != _latchedFailures) {
      _latchedFailures = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _ended = false;
        if (mounted) widget.onEndSuppressionChanged?.call(false);
      });
    }
    if (!mine) return const SizedBox.shrink();
    final label = context.l10n.endConversation;
    // Experimental design: the bar also holds Pause, so the button reads End; a screen reader still
    // hears the full name.
    final shown = ExperimentalDesign.of(context) ? context.l10n.endConversationShort : label;
    final text = FittedBox(
      fit: BoxFit.scaleDown,
      child: Text(shown,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: OmiType.headline.copyWith(color: widget.onTray ? Colors.white : OmiColors.danger)),
    );
    Future<void> end() async {
      final capture = context.read<CaptureProvider>();
      // Checked again at the tap: the capture may have moved on since the last build.
      final v3 = context.read<ConversationsV3Provider?>();
      if (_ended ||
          !LiveConversationEndButton.phoneCaptures(conversation, capture,
              currentLiveId: v3?.live?.id, liveCaptureDeviceId: v3?.live?.v3?.captureDeviceId)) {
        return;
      }
      _ended = true;
      HapticFeedback.mediumImpact();
      final setEndSuppressed = widget.onEndSuppressionChanged;
      setEndSuppressed?.call(true);
      final previousFinish = v3?.finishRow;
      final failuresAtTap = v3?.finishFailures;
      var started = false;
      var closed = false;
      try {
        final finish =
            capture.forceProcessingCurrentConversation(manualFinish: true, liveConversationId: conversation.id);
        started = v3?.finishRow != null && !identical(v3!.finishRow, previousFinish);
        await finish;
        closed = true;
      } catch (_) {
        // The close kept the capture. End stays on detail so the user can retry it.
        return;
      } finally {
        // A closed window with a published finish stays latched; only a failed close restores End.
        if (!(closed && started)) {
          _ended = false;
          setEndSuppressed?.call(false);
        } else {
          _latchedFailures = failuresAtTap;
        }
      }
      if (!context.mounted || !started || ModalRoute.of(context)?.isCurrent != true) return;
      // A filtered Home cannot show the Processing row; the result lands on this detail instead.
      if (context.read<ConversationProvider?>()?.showsDefaultHome != true) return;
      context.read<HomeProvider?>()?.showNewestOnHome();
      HomeNavigation.returnHome(context);
    }

    return Padding(
      padding: EdgeInsetsDirectional.only(start: widget.leadingGap),
      child: Semantics(
        button: true,
        label: label,
        excludeSemantics: true,
        child: Material(
          key: const Key('live_conversation_end'),
          color: Colors.transparent,
          child: Ink(
            height: 56,
            decoration: ExperimentalDesign.of(context)
                ? null
                : BoxDecoration(
                    color: OmiColors.surface1,
                    borderRadius: OmiRadius.pillAll,
                    border: Border.all(color: OmiColors.border, width: 1),
                  ),
            child: InkWell(
              borderRadius: OmiRadius.pillAll,
              onTap: end,
              // At most half the bar, so Ask Omi keeps its room; a long translation scales down on one
              // line, then ellipsizes, rather than overflowing a 320pt screen.
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.45),
                child: ExperimentalDesign.of(context)
                    // As wide as its short label needs, so Ask Omi keeps the middle of the bar.
                    ? IntrinsicWidth(
                        child: widget.onTray
                            ? Container(
                                height: 56,
                                alignment: Alignment.center,
                                padding: const EdgeInsets.symmetric(horizontal: 22),
                                decoration: BoxDecoration(color: OmiColors.danger, borderRadius: OmiRadius.pillAll),
                                child: text,
                              )
                            : FooterGlassSurface(
                                height: 56,
                                raised: true,
                                padding: const EdgeInsets.symmetric(horizontal: 22),
                                onTap: end,
                                child: text),
                      )
                    : Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Center(child: text)),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
