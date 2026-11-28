// The live row and the Finishing… row: what is capturing now, and what the reader just ended.
// Both are drawn with HomeRowShell, so they line up with every other Home row.

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/home/home_model.dart';
import 'package:omi/pages/conversations/home/home_row_shell.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/ui/components/local_stt_recovery_notice.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// The one live row, first in Today while anything captures.
class HomeLiveRowView extends StatelessWidget {
  const HomeLiveRowView({super.key, required this.row});

  final HomeLiveRow row;

  @override
  Widget build(BuildContext context) {
    final failure = context.select<CaptureProvider, Object?>((c) => c.localSttFailure);
    final Widget body = switch (row.kind) {
      HomeLiveKind.call => const _CallRow(),
      // Transcribe Later keeps its own controls (Pause, New recording, Stop).
      HomeLiveKind.transcribeLater => const ConversationCaptureWidget(),
      // The server's conversation in progress is its own row, as every conversation is: its live tile,
      // "Listening" until it has a title, its length, and no snippet or date.
      HomeLiveKind.conversation => ConversationListItem(
          key: ValueKey(row.conversation!.id),
          conversation: row.conversation!,
          conversationIdx: 0,
          date: homeDay(row.conversation!.startedAt ?? row.conversation!.createdAt),
        ),
      // A capture the server shows no conversation for yet.
      HomeLiveKind.capture => const _CaptureRow(),
    };
    if (failure == null || row.kind == HomeLiveKind.call || row.kind == HomeLiveKind.transcribeLater) return body;
    final capture = context.read<CaptureProvider>();
    return Column(
      key: const Key('home_live_row'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        body,
        LocalSttRecoveryNotice(
          failure: capture.localSttFailure!,
          onRetry: capture.retryLocalTranscription,
          onSetup: () => routeToPage(context, const TranscriptionSettingsPage()),
        ),
      ],
    );
  }
}

class _CaptureRow extends StatelessWidget {
  const _CaptureRow();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final (state, source, verified, admitted, preview, device, socketReady, _) = context.select<CaptureProvider,
        (CaptureDisplayState, String?, bool, bool, LivePreviewController?, BtDevice?, bool, int)>(
      (capture) => (
        EpisodePresentation.displayState(capture),
        capture.liveCaptureSource,
        capture.pendantCaptureVerified,
        capture.liveWordsShown,
        capture.livePreview,
        capture.recordingDevice,
        capture.transcriptServiceReady,
        // Rebuilds the row when final text or photos arrive.
        capture.segmentsPhotosVersion,
      ),
    );
    final capture = context.read<CaptureProvider>();
    final micTaken = state == CaptureDisplayState.paused && capture.isCallActive;
    final copy = captureCardCopy(l10n, state, micTaken: micTaken, socketDown: !socketReady);
    final listening = EpisodePresentation.isListening(state);
    final noAudio = state == CaptureDisplayState.noAudio;
    final title = copy.status;

    final canShowPreview = source != null &&
        source != 'phone' &&
        device?.type == DeviceType.omi &&
        verified &&
        admitted &&
        listening &&
        capture.segments.isEmpty &&
        capture.photos.isEmpty;

    Widget subtitle() {
      if (!listening) {
        return Text(
          copy.detail ?? l10n.live,
          key: const Key('home_live_row_subtitle'),
          style: HomeRowShell.subtitleStyle.copyWith(color: copy.warning ? OmiColors.warning : null),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        );
      }
      return ListenableBuilder(
        listenable: preview ?? const AlwaysStoppedAnimation<double>(0),
        builder: (context, _) {
          final latest = canShowPreview && preview?.admitted == true ? preview!.latestLine?.trim() : null;
          // Only an admitted, verified pendant's preview words; anything else stays status-only.
          return Text(
            latest == null || latest.isEmpty ? l10n.live : latest,
            key: const Key('home_live_row_subtitle'),
            style: HomeRowShell.subtitleStyle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          );
        },
      );
    }

    void open() => routeToPage(context, LiveEpisodePage(topConversationId: capture.topConversationId));

    void reconnect() {
      OmiHaptics.medium();
      capture.reconnectRecordingPendant().catchError((Object _) {
        // Say so where the reader is, with the way forward: try the reconnect again.
        if (context.mounted) {
          OmiFeedback.error(context, l10n.somethingWentWrong, actionLabel: l10n.retry, onAction: reconnect);
        }
      });
    }

    final Widget dot = switch (state) {
      CaptureDisplayState.reconnecting ||
      CaptureDisplayState.connecting =>
        const OmiSpinner(size: OmiSpinnerSize.small),
      _ when copy.warning || noAudio => Icon(Icons.circle, size: 10, color: OmiColors.warning),
      CaptureDisplayState.paused ||
      CaptureDisplayState.muted =>
        Icon(Icons.circle, size: 10, color: OmiColors.textTertiary),
      _ => const OmiBreathingDot(),
    };

    return CaptureStateAnnouncement(
      message: captureStateLabel(l10n, state),
      child: HomeRowShell(
        key: const Key('home_live_row'),
        tile: HomeRowTile(outline: copy.warning || noAudio ? OmiColors.warning : null, child: dot),
        title: title,
        subtitleWidget: subtitle(),
        semanticsLabel: [title, copy.detail ?? l10n.live].join(', '),
        semanticsHint: l10n.liveTranscript,
        // No chevron: no Home row carries one; the row itself is the tap target.
        trailing: noAudio
            ? HomeRowAction(key: const Key('home_live_reconnect'), label: l10n.reconnect, onPressed: reconnect)
            : null,
        actionTrailing: noAudio,
        onTap: open,
      ),
    );
  }
}

class _CallRow extends StatelessWidget {
  const _CallRow();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final call = context.watch<PhoneCallProvider>();
    final title = switch (call.callState) {
      PhoneCallState.connecting => l10n.callStateConnecting,
      PhoneCallState.ringing => l10n.callStateRinging,
      _ => l10n.listening,
    };
    final elapsed = call.callState == PhoneCallState.active ? call.callDuration : null;
    final lastLine = call.transcriptSegments.lastOrNull?.text.trim();
    final parts = [
      if (elapsed != null) LiveCaptureCard.formatElapsed(elapsed),
      if (lastLine != null && lastLine.isNotEmpty) '“$lastLine”',
    ];
    return HomeRowShell(
      key: const Key('home_live_call_row'),
      tile: HomeRowTile(child: Icon(Icons.phone_in_talk_rounded, size: 18, color: OmiColors.textPrimary)),
      title: title,
      subtitle: parts.isEmpty ? null : parts.join(' · '),
      semanticsHint: l10n.openCall,
      onTap: () => routeToPage(context, const ActiveCallPage()),
    );
  }
}

/// The conversation the reader just ended: tappable, and replaced in place by the server's row.
class HomeFinishingRowView extends StatelessWidget {
  const HomeFinishingRowView({super.key, required this.row});

  final HomeFinishingRow row;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final id = context.select<ConversationsV3Provider?, String?>((p) => p?.finishConversationId);
    final seconds = row.conversation.getDurationInSeconds();
    final parts = [if (seconds > 0) OmiDuration.compact(seconds, l10n), l10n.writingSummaryStatus];

    void open() {
      // Wherever Home found its row: the list, or the processing rows the list has not caught up with.
      final list = context.read<ConversationProvider>();
      final target = id == null
          ? null
          : [...list.conversations, ...list.processingConversations]
              .where((c) => c.id == id && c.id != OptimisticProcessingPlaceholder.id)
              .firstOrNull;
      if (target != null) {
        routeToPage(context, ConversationDetailPage(conversation: target));
        return;
      }
      // Nothing to open yet: say so instead of doing nothing.
      OmiFeedback.info(context, l10n.homeFinishingOpensWhenReady);
    }

    return HomeRowShell(
      key: const Key('home_finishing_row'),
      tile: const HomeRowTile(child: OmiSpinner(size: OmiSpinnerSize.small)),
      title: l10n.episodeFinishingUp,
      subtitle: parts.join(' · '),
      onTap: open,
    );
  }
}
