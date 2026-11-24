import 'dart:async';

import 'package:flutter/material.dart';

import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/finished_capture_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/capture/finish_outcome.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// What the live page showed when Finish was tapped. The page keeps it on screen until the server
/// has answered, and after a failure, so the reader never watches their transcript vanish before
/// the request that could fail (ux-contract §17.3).
typedef HeldCapture = ({List<TranscriptSegment> segments, List<ConversationPhoto> photos});

HeldCapture? holdCapture(CaptureProvider provider) => provider.segments.isEmpty && provider.photos.isEmpty
    ? null
    : (segments: List<TranscriptSegment>.of(provider.segments), photos: List<ConversationPhoto>.of(provider.photos));

/// Finish the live capture: the one path behind the live page's Finish, Home's Wrap Up and the
/// record button's stop. It always answers with a [FinishOutcome]; it never throws.
///
/// [retry] sends Process Now again after a failed Finish even when the page shows nothing new: the
/// failed request processed nothing, and the controller already moved its transcript aside.
///
/// [owned] allows Process Now when the live page has matched its window to the capture before any
/// transcript arrives.
Future<FinishOutcome> finishLiveCapture(
  BuildContext context,
  CaptureProvider provider, {
  EpisodeProvider? episodes,
  bool retry = false,
  bool owned = false,
}) async {
  final v3Feedback = context.read<ConversationsV3Provider?>()?.finishFeedbackEnabled ?? false;
  final preview = provider.livePreview;
  final closed = provider.lastServerClose;
  final recentClose =
      closed != null && DateTime.now().difference(closed.at) < const Duration(minutes: 5) ? closed : null;
  final finished = provider.lastClientFinish;
  final closeIsLatest = recentClose != null && (finished == null || recentClose.at.isAfter(finished.at));
  // Words the preview heard before the last close or Finish were already processed (the preview
  // keeps its lines across both). A new preview session starts its count again.
  final baseline = closeIsLatest
      ? (words: recentClose.previewWords, session: recentClose.previewSession)
      : finished == null
          ? null
          : (words: finished.previewWords, session: finished.previewSession);
  final heardSinceClose = preview != null &&
      (baseline == null || baseline.session != preview.sessionGeneration
          ? preview.lines.isNotEmpty
          : preview.totalWordsSeen > baseline.words);
  final hadContent = provider.segments.isNotEmpty || provider.photos.isNotEmpty || heardSinceClose;
  // The phone's own recording always stops through Process Now (Transcribe Later finalizes its file
  // instead): the server, not the page, knows whether speech arrived that has no line yet.
  // A phone recorder still restoring coordinator ownership has no source yet, but is still this phone's.
  final phoneOwns = provider.liveCaptureSource == ConversationSource.phone.name ||
      (provider.liveCaptureSource == null && EpisodePresentation.streamingSource(provider) == 'phone');
  if (hadContent || retry || phoneOwns || owned || (v3Feedback && provider.verifiedLiveServerRecordingId != null)) {
    final previousFinish = provider.lastClientFinish;
    provider.noteClientFinish();
    FinishOutcome outcome;
    try {
      // Ending the capture fires the shared finalize hook, which closes the episode.
      final answer = await provider.finishCaptureWithOutcome();
      // A retry re-sends what the page held after a failed Finish; a phone page with no line
      // showed nothing, so "nothing to process yet" is the honest answer there (C5).
      outcome = v3Feedback && answer.absence == ProcessAbsence.notFound
          ? const FinishFailed(FinishFailure.exception)
          : FinishOutcome.fromProcess(
              answer,
              heardSomething: hadContent || retry || owned || v3Feedback,
            );
    } on FinishMadeNoRequest {
      outcome = const FinishSavedForLater();
    } catch (_) {
      outcome = const FinishFailed(FinishFailure.exception);
    }
    // Nothing was processed, so the next Finish must still send it.
    if (outcome is FinishFailed || outcome is FinishNotReceived) provider.lastClientFinish = previousFinish;
    return outcome;
  }
  try {
    if (provider.liveCaptureSource == null) await provider.stopStreamRecording();
  } catch (_) {
    return const FinishFailed(FinishFailure.exception);
  }
  if (episodes != null && episodes.enabled) episodes.onLiveFinalized();
  // The server closed it on its own just before the tap: open that one.
  if (closeIsLatest) return FinishProcessing(recentClose.id);
  return const FinishNothingNew();
}

/// The page a successful Finish opens, or null when the outcome opens nothing.
Widget? finishedPageFor(FinishOutcome outcome) => switch (outcome) {
      FinishOpened(:final conversation) => ConversationDetailPage(conversation: conversation),
      FinishProcessing(:final recordingId) => FinishedCapturePage(recordingId: recordingId),
      _ => null,
    };

/// The sentence that tells the reader what Finish did when it opens nothing.
String? finishMessage(BuildContext context, FinishOutcome outcome) {
  final l10n = context.l10n;
  return switch (outcome) {
    FinishNothingNew(alreadySaved: true) => l10n.finishAlreadySaved,
    FinishNothingNew() => l10n.finishNothingNew,
    FinishDiscarded() => l10n.discardedOnlyRecording,
    FinishNotReceived() => l10n.finishAudioNotReceived,
    FinishFailed(reason: FinishFailure.noAnswer) => l10n.finishFailedOffline,
    FinishFailed() => l10n.finishFailed,
    _ => null,
  };
}

/// Where Finish was tapped.
enum FinishEntry {
  /// The live page: it is replaced by the result, and stays (transcript on screen) on a failure.
  livePage,

  /// Home (Wrap Up, the record button): the result is pushed over Home.
  home,
}

/// Shows [outcome] (ux-contract §17.1): the result opens from every entry point, a failure keeps
/// the reader where they are with Try Again, and nothing-to-do says why. Returns true when the live
/// page should stay (a failure, or audio still on its way).
bool presentFinishOutcome(
  BuildContext context,
  FinishOutcome outcome, {
  required FinishEntry entry,
  VoidCallback? onRetry,
}) {
  final v3 = context.read<ConversationsV3Provider?>();
  final homeShowsProcessing = outcome is FinishProcessing &&
      v3?.finishRow != null &&
      context.read<ConversationProvider?>()?.showsDefaultHome == true;
  final page = homeShowsProcessing ? null : finishedPageFor(outcome);
  final message = finishMessage(context, outcome);
  final stays = outcome is FinishFailed || outcome is FinishNotReceived;
  if (homeShowsProcessing ||
      page != null ||
      outcome is FinishSavedForLater ||
      (outcome is FinishNothingNew && outcome.alreadySaved)) {
    // Home is where the result lands when the reader goes back, its new row in view (C13).
    context.read<HomeProvider?>()?.showNewestOnHome();
  }
  if (message != null) {
    if (outcome is FinishFailed) {
      OmiFeedback.error(context, message, actionLabel: context.l10n.tryAgain, onAction: onRetry);
    } else {
      OmiFeedback.info(context, message);
    }
  }
  if (stays) return true;
  if (entry == FinishEntry.home) {
    if (page != null) unawaited(routeToPage(context, page));
    return false;
  }
  // A swipe back during the finish has already popped the live route; it only stays mounted while
  // it animates out, and a pop then would take Home with it and leave the navigator empty.
  final route = ModalRoute.of(context);
  if (route == null || !route.isCurrent) return false;
  if (page != null) {
    unawaited(Navigator.of(context).pushReplacement(omiPageRoute(builder: (_) => page)));
  } else {
    Navigator.of(context).pop();
  }
  return false;
}

/// Try Again for a Finish that failed on Home: send it again and show its outcome there.
Future<void> retryFinishFromHome(BuildContext context, CaptureProvider provider) async {
  final outcome = await finishLiveCapture(context, provider, episodes: context.read<EpisodeProvider?>(), retry: true);
  if (!context.mounted) return;
  presentFinishOutcome(context, outcome,
      entry: FinishEntry.home, onRetry: () => retryFinishFromHome(context, provider));
}

/// The record button with the microphone blocked: say so, and offer the one way to fix it
/// (ux-contract §15). Every tap answers the same way until it is allowed.
void showMicBlocked(BuildContext context) => OmiFeedback.error(
      context,
      context.l10n.micBlockedCannotRecord,
      actionLabel: context.l10n.openSettings,
      onAction: () => unawaited(openAppSettings()),
    );
