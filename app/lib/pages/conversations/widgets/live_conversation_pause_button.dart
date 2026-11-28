import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/conversations/widgets/live_conversation_end_button.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/footer_glass.dart';

/// Pauses the capture, or resumes one the reader paused: the action of Home's live card.
Future<void> toggleCapturePause(BuildContext context, CaptureProvider provider) async {
  final phone = provider.liveCaptureSource == 'phone';
  try {
    OmiHaptics.medium();
    if (provider.isPaused) {
      await provider.resumeCapture();
      if (phone && !provider.isPaused) PlatformManager.instance.analytics.phoneMicRecordingStarted();
    } else {
      await provider.pauseCapture();
      if (phone) PlatformManager.instance.analytics.phoneMicRecordingStopped();
    }
  } catch (_) {
    // Say so rather than leave an unhandled future.
    if (context.mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    return;
  }
  PlatformManager.instance.analytics.recordingMuteToggled(
    isMuted: provider.isPaused,
    recordingType: phone ? 'phone_mic' : 'device',
  );
}

/// Experimental design: Pause at the start of a live conversation's bar, opposite End. A frosted
/// circle that pauses the capture this phone is running and resumes it, the same action as the
/// Pause on Home's live card. Shown only where End is: for the conversation this phone captures.
/// Nothing while the capture cannot be paused (a photo device) or the system holds the microphone.
class LiveConversationPauseButton extends StatelessWidget {
  const LiveConversationPauseButton(
      {super.key, required this.conversation, this.trailingGap = 10, this.style = FooterGlassStyle.blur});

  final FooterGlassStyle style;

  final ServerConversation conversation;
  final double trailingGap;

  /// A pause the reader chose, as Home's live card reads it.
  static bool readerPaused(CaptureProvider capture) {
    final source = capture.liveCaptureSource;
    if (source != null && source != 'phone') {
      return capture.isPaused && capture.recordingState == RecordingState.pause;
    }
    return capture.isPhoneMicPaused || capture.isPaused;
  }

  static bool _available(CaptureProvider capture) {
    final paused = readerPaused(capture);
    final micTaken = captureInterruption(
          interrupted: capture.recordingState == RecordingState.interrupted,
          readerPaused: paused,
          osHoldsMic: capture.isCallActive,
        ) ==
        CaptureInterruption.micTaken;
    return !micTaken && LiveCaptureCard.canPause(capture.recordingDevice, source: capture.liveCaptureSource);
  }

  @override
  Widget build(BuildContext context) {
    final currentLiveId = context.select<ConversationsV3Provider?, String?>((v3) => v3?.live?.id);
    final liveDevice = context.select<ConversationsV3Provider?, String?>((v3) => v3?.live?.v3?.captureDeviceId);
    final shown = context.select<CaptureProvider?, bool>(
      (capture) =>
          capture != null &&
          LiveConversationEndButton.phoneCaptures(conversation, capture,
              currentLiveId: currentLiveId, liveCaptureDeviceId: liveDevice) &&
          _available(capture),
    );
    if (!shown) return const SizedBox.shrink();
    final paused = context.select<CaptureProvider, bool>(readerPaused);
    final label = paused ? context.l10n.resume : context.l10n.pause;
    void toggle() => toggleCapturePause(context, context.read<CaptureProvider>());
    return Padding(
      padding: EdgeInsetsDirectional.only(end: trailingGap),
      child: Semantics(
        button: true,
        label: label,
        excludeSemantics: true,
        onTap: toggle,
        child: FooterGlassSurface(
          key: const Key('live_conversation_pause'),
          height: 56,
          circle: true,
          raised: true,
          style: style,
          onTap: toggle,
          child: Icon(paused ? Icons.play_arrow_rounded : Icons.pause_rounded,
              size: 26, color: style == FooterGlassStyle.glass ? Colors.white : OmiColors.textPrimary),
        ),
      ),
    );
  }
}
