import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';
import 'package:omi/widgets/speaker_label.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversations/widgets/capture_recovery_banner.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/widgets/conversation_photo_image.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/photos_grid.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';

import 'capture_state_header.dart';

/// Switch the home IndexedStack to Conversations *before* popping the capturing
/// route so the user lands on that tab with no flash of the previous page.
void switchHomeToConversationsTab(BuildContext context) {
  context.read<HomeProvider>().setIndex(1);
}

class ConversationCapturingPage extends StatefulWidget {
  final String? topConversationId;

  const ConversationCapturingPage({super.key, this.topConversationId});

  @override
  State<ConversationCapturingPage> createState() => _ConversationCapturingPageState();
}

class _ConversationCapturingPageState extends State<ConversationCapturingPage> {
  final TranscriptScrollStateStore _transcriptScrollStateStore = TranscriptScrollStateStore();

  final scaffoldKey = GlobalKey<ScaffoldState>();
  bool _mutePending = false;

  @override
  void initState() {
    super.initState();
    ListenClientState.instance.capturePageOpened();
  }

  TranscriptScrollState _scrollStateFor(String sessionId) {
    return _transcriptScrollStateStore.forSession(sessionId);
  }

  Future<void> _toggleMute(CaptureProvider provider) async {
    if (_mutePending) return;
    setState(() => _mutePending = true);
    try {
      HapticFeedback.mediumImpact();
      final phone = provider.liveCaptureSource == 'phone';
      if (provider.isPaused) {
        await provider.resumeCapture();
        if (phone) PlatformManager.instance.analytics.phoneMicRecordingStarted();
      } else {
        await provider.pauseCapture();
        if (phone) PlatformManager.instance.analytics.phoneMicRecordingStopped();
      }
    } catch (_) {
      if (mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _mutePending = false);
    }
  }

  @override
  void dispose() {
    ListenClientState.instance.capturePageClosed();
    super.dispose();
  }

  @visibleForTesting
  Future<void> debugStopConversation(CaptureProvider provider) => _stopConversation(provider);

  /// Finish: the one stop. No confirmation: Finish is explicit, and it processes the conversation
  /// (a phone recording stops first; a pendant it paused resumes afterwards).
  Future<void> _stopConversation(CaptureProvider provider) async {
    await provider.finishCapture();
    if (!mounted) return;
    switchHomeToConversationsTab(context);
    Navigator.of(context).pop();
  }

  /// The live page's state, resolved exactly as the conversation list's capture card resolves it
  /// (`liveCaptureDisplayState`): an audio interruption, a mute or a call is Paused, a terminal
  /// transcription failure or offline buffering is named as such, otherwise Listening.
  CaptureDisplayState _displayState(CaptureProvider provider, {required bool capturingPhotos}) {
    return liveCaptureDisplayState(
      audioInterrupted: provider.recordingState == RecordingState.interrupted,
      paused: provider.isPaused || provider.isCallActive,
      transcriptionUnavailable: provider.terminalTranscriptionFailure != null,
      bufferingFor: provider.customSttBufferingDuration,
      capturingPhotos: capturingPhotos,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        final effectivelyMuted = provider.isPaused || provider.isCallActive;
        final connectivity = context.watch<ConnectivityProvider>();
        final usage = context.watch<UsageProvider>();
        final photoChannelActive = _photoChannelActive(deviceProvider.connectedDevice);
        final transcriptionInterrupted = provider.recordingState == RecordingState.interrupted;
        final transcriptSessionId =
            provider.activeCaptureSessionId ?? widget.topConversationId ?? 'pending-live-capture';
        final transcriptScrollState = _scrollStateFor(transcriptSessionId);
        return Scaffold(
          key: scaffoldKey,
          backgroundColor: OmiColors.surface0,
          appBar: ConversationStateAppBar(
            state: _displayState(provider, capturingPhotos: provider.photos.isNotEmpty),
            bufferingFor: provider.customSttBufferingDuration,
            sourceLabel: switch (provider.liveCaptureSource) {
              null => null,
              'phone' => context.l10n.captureSourcePhoneMic,
              final source => CaptureSources.label(context, source),
            },
          ),
          body: Column(
            children: [
              const CaptureRecoveryBanner(),
              _buildUnsyncedWalIndicator(provider),
              Expanded(
                child: provider.segments.isEmpty && provider.photos.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(OmiSpacing.xxl, 50, OmiSpacing.xxl, 0),
                          child: Text(
                            textAlign: TextAlign.center,
                            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                            _liveCaptureEmptyStateText(
                              provider,
                              connectivity: connectivity,
                              usage: usage,
                              photoChannelActive: photoChannelActive,
                              transcriptionInterrupted: transcriptionInterrupted,
                            ),
                          ),
                        ),
                      )
                    : provider.photos.isNotEmpty
                        ? _buildChronologicalTimeline(provider, transcriptSessionId, transcriptScrollState,
                            widget.topConversationId ?? provider.topConversationId)
                        : getTranscriptWidget(
                            false,
                            provider.segments,
                            provider.photos,
                            deviceProvider.connectedDevice,
                            bottomMargin: 0,
                            taggingSegmentIds: provider.taggingSegmentIds,
                            transcriptKey: ValueKey('live-transcript-$transcriptSessionId'),
                            followLatest: true,
                            scrollState: transcriptScrollState,
                            jumpToLatestButtonBottom: MediaQuery.paddingOf(context).bottom + 84,
                            contentVersion: provider.segmentsPhotosVersion,
                            editSegment: (segmentId, speakerId) => _nameSpeaker(segmentId, speakerId, provider),
                          ),
              ),
            ],
          ),
          floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
          // Pause/Resume (a pause glyph: mics belong to Ask Omi) and Finish, the one stop.
          floatingActionButton:
              (provider.liveCaptureSource != null || provider.segments.isNotEmpty || provider.photos.isNotEmpty)
                  ? Row(
                      mainAxisSize: MainAxisSize.min,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        if (provider.liveCaptureSource != null &&
                            LiveCaptureCard.canPause(provider.recordingDevice, source: provider.liveCaptureSource)) ...[
                          OmiIconButton.filled(
                            key: const Key('capture_pause_button'),
                            icon: Icon(effectivelyMuted ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 26),
                            label: effectivelyMuted ? context.l10n.resume : context.l10n.pause,
                            diameter: 52,
                            fillColor: OmiColors.surface3,
                            onPressed: _mutePending || provider.isCallActive ? null : () => _toggleMute(provider),
                          ),
                          const SizedBox(width: OmiSpacing.sm),
                        ],
                        OmiButton(
                          key: const Key('process_now_button'),
                          label: context.l10n.finish,
                          leading: const Icon(Icons.check_rounded),
                          onPressed: () => _stopConversation(provider),
                        ),
                      ],
                    )
                  : null,
        );
      },
    );
  }

  /// Builds a chronological timeline interleaving photo groups and transcript segments.
  Widget _buildChronologicalTimeline(
    CaptureProvider provider,
    String sessionId,
    TranscriptScrollState scrollState,
    String? conversationId,
  ) {
    final photos = List<ConversationPhoto>.from(provider.photos)..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    final segments = provider.segments;
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final names = SpeakerNames.forSegments(segments, people: people, l10n: context.l10n);

    // Group consecutive photos taken within 30 seconds of each other
    final List<List<ConversationPhoto>> photoGroups = [];
    if (photos.isNotEmpty) {
      List<ConversationPhoto> currentGroup = [photos.first];
      for (int i = 1; i < photos.length; i++) {
        if (photos[i].createdAt.difference(photos[i - 1].createdAt).inSeconds <= 30) {
          currentGroup.add(photos[i]);
        } else {
          photoGroups.add(currentGroup);
          currentGroup = [photos[i]];
        }
      }
      photoGroups.add(currentGroup);
    }

    final leadingItems = [
      for (var index = 0; index < photoGroups.length; index++)
        Padding(
          padding: EdgeInsets.only(top: index == 0 ? 16 : 0),
          child: _buildPhotoGroupTimelineItem(photoGroups[index], photos, conversationId),
        ),
    ];

    return TranscriptWidget(
      key: ValueKey('live-transcript-$sessionId'),
      segments: segments,
      horizontalMargin: false,
      topMargin: false,
      separator: false,
      canDisplaySeconds: false,
      bottomMargin: 0,
      followLatest: true,
      scrollState: scrollState,
      jumpToLatestButtonBottom: MediaQuery.paddingOf(context).bottom + 84,
      contentVersion: provider.segmentsPhotosVersion,
      layoutIdentity: 'photo-timeline',
      leadingItems: leadingItems,
      leadingItemIds: photoGroups.map((group) => group.first.id).toList(),
      segmentBuilder: (context, segment, index) => _buildTranscriptTimelineItem(segment, provider, people, names),
    );
  }

  Widget _buildPhotoGroupTimelineItem(
    List<ConversationPhoto> group,
    List<ConversationPhoto> allPhotos,
    String? conversationId,
  ) {
    final timeStr = OmiDateFormat.of(context).time(group.first.createdAt);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          // Camera icon avatar
          const Column(
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: OmiColors.surface2,
                child: Icon(Icons.camera_alt, size: 16, color: OmiColors.textSecondary),
              ),
              SizedBox(height: 2),
            ],
          ),
          const SizedBox(width: 8),
          // Photo group bubble
          Flexible(
            child: Container(
              constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.7),
              decoration: BoxDecoration(
                color: OmiColors.surface1,
                borderRadius: const BorderRadius.all(Radius.circular(18)),
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 4, offset: const Offset(0, 1)),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Grid of photos in this group
                  ClipRRect(
                    borderRadius: const BorderRadius.only(topLeft: Radius.circular(18), topRight: Radius.circular(18)),
                    child: group.length == 1
                        ? GestureDetector(
                            onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(group.first), conversationId),
                            child: SizedBox(
                              width: double.infinity,
                              child: ConversationPhotoImage(
                                photo: group.first,
                                conversationId: conversationId,
                                fit: BoxFit.cover,
                              ),
                            ),
                          )
                        : _buildPhotoGrid(group, allPhotos, conversationId),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.camera_alt, size: 12, color: OmiColors.textTertiary),
                        const SizedBox(width: 4),
                        Text(
                          group.length > 1
                              ? '$timeStr · ${context.l10n.conversationPhotosCount(group.length)}'
                              : timeStr,
                          style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPhotoGrid(List<ConversationPhoto> group, List<ConversationPhoto> allPhotos, String? conversationId) {
    if (group.length == 2) {
      return Row(
        children: group
            .map(
              (photo) => Expanded(
                child: GestureDetector(
                  onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo), conversationId),
                  child: AspectRatio(
                    aspectRatio: 1,
                    child: ConversationPhotoImage(photo: photo, conversationId: conversationId, fit: BoxFit.cover),
                  ),
                ),
              ),
            )
            .toList(),
      );
    }
    // 3+ photos: show first two large, rest smaller below
    final firstRow = group.take(2).toList();
    final secondRow = group.skip(2).toList();
    return Column(
      children: [
        Row(
          children: firstRow
              .map(
                (photo) => Expanded(
                  child: GestureDetector(
                    onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo), conversationId),
                    child: AspectRatio(
                      aspectRatio: 1,
                      child: ConversationPhotoImage(photo: photo, conversationId: conversationId, fit: BoxFit.cover),
                    ),
                  ),
                ),
              )
              .toList(),
        ),
        if (secondRow.isNotEmpty)
          Row(
            children: [
              ...secondRow.map(
                (photo) => Expanded(
                  child: GestureDetector(
                    onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo), conversationId),
                    child: AspectRatio(
                      aspectRatio: 1,
                      child: ConversationPhotoImage(photo: photo, conversationId: conversationId, fit: BoxFit.cover),
                    ),
                  ),
                ),
              ),
              // Fill remaining space if odd number
              if (secondRow.length < 2) const Expanded(child: SizedBox()),
            ],
          ),
      ],
    );
  }

  void _openPhotoViewer(List<ConversationPhoto> allPhotos, int index, String? conversationId) {
    MediaViewerPage.open(
      context,
      items: mediaItemsForPhotos(allPhotos, conversationId),
      initialIndex: index >= 0 ? index : 0,
    );
  }

  void _nameSpeaker(String segmentId, int speakerId, CaptureProvider provider) {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }
    final suggestion = provider.suggestionsBySegmentId.values.firstWhere(
      (s) => s.speakerId == speakerId,
      orElse: () => SpeakerLabelSuggestionEvent.empty(),
    );
    showNameSpeakerSheet(
      context,
      speakerId: speakerId,
      segmentId: segmentId,
      segments: provider.segments,
      suggestion: suggestion,
      defaultApplyToSpeaker: true,
      onSpeakerAssigned: (speakerId, personId, personName, segmentIds, applyToSpeaker) async {
        return provider.assignSpeakerToConversation(speakerId, personId, personName, segmentIds,
            applyToSpeaker: applyToSpeaker);
      },
    );
  }

  void _editSegmentSpeaker(TranscriptSegment segment, CaptureProvider provider) =>
      _nameSpeaker(segment.id, segment.speakerId, provider);

  Widget _buildTranscriptTimelineItem(
      TranscriptSegment segment, CaptureProvider provider, List<Person> people, SpeakerNames names) {
    final bool isUser = segment.isUser;
    final name = names.forSegment(segment, person: personById(people, segment.personId));
    Widget avatar() => Semantics(
          button: true,
          label: context.l10n.identifySpeaker,
          excludeSemantics: true,
          onTap: () => _editSegmentSpeaker(segment, provider),
          child: GestureDetector(
            onTap: () => _editSegmentSpeaker(segment, provider),
            child: const Column(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: OmiColors.surface2,
                  child: Icon(Icons.person, size: 16, color: OmiColors.textSecondary),
                ),
                SizedBox(height: 2),
              ],
            ),
          ),
        );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) ...[
            avatar(),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: GestureDetector(
              onTap: () => _editSegmentSpeaker(segment, provider),
              child: Container(
                constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: isUser ? OmiColors.surface3 : OmiColors.surface2,
                  borderRadius: const BorderRadius.all(Radius.circular(18)),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 4, offset: const Offset(0, 1)),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name, style: OmiType.caption.copyWith(color: OmiColors.textSecondary)),
                    const SizedBox(height: 4),
                    Text(segment.text, style: OmiType.subhead.copyWith(height: 1.4)),
                  ],
                ),
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 8),
            avatar(),
          ],
        ],
      ),
    );
  }

  /// Photos reach a live conversation only through camera-capable wearables
  /// (Ray-Ban Meta, OpenGlass). A phone-mic session has no photo channel, so
  /// its empty state must not promise one (#14473).
  bool _photoChannelActive(BtDevice? connectedDevice) {
    final type = connectedDevice?.type;
    return type == DeviceType.raybanMeta || type == DeviceType.openglass;
  }

  /// The live-capture empty state names only what this session can actually
  /// produce, and swaps in a truthful state line when the transcript pipeline
  /// is degraded instead of promising "waiting" forever (#14473): an
  /// out-of-credits plan can never produce a transcript while waiting, a
  /// terminal STT failure means the audio is only being saved (the shared
  /// outage sentence — the app bar names the same moment the same way), an
  /// offline device is waiting on the network, and `interrupted` means the
  /// transcription socket dropped and is reconnecting.
  String _liveCaptureEmptyStateText(
    CaptureProvider provider, {
    required ConnectivityProvider connectivity,
    required UsageProvider usage,
    required bool photoChannelActive,
    required bool transcriptionInterrupted,
  }) {
    if (usage.isOutOfCredits) return context.l10n.transcriptionUnavailableRecordingSaved;
    if (provider.terminalTranscriptionFailure != null) {
      return context.l10n.transcriptionUnavailableRecordingContinues;
    }
    if (!connectivity.isConnected) return context.l10n.recordingOfflineTranscriptWillCatchUp;
    if (transcriptionInterrupted) return context.l10n.transcriptionPausedReconnecting;
    if (!photoChannelActive) return context.l10n.listeningTranscriptWillAppear;
    return context.l10n.waitingForTranscriptOrPhotos;
  }

  Widget _buildUnsyncedWalIndicator(CaptureProvider provider) {
    final unsyncedWals = provider.unsyncedSessionWals;
    final inFlightSeconds = provider.inFlightAudioSeconds;
    final totalSeconds = unsyncedWals.fold<int>(0, (sum, w) => sum + w.seconds) + inFlightSeconds;
    if (totalSeconds <= 5) return const SizedBox.shrink();
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    final label = minutes > 0 ? '${minutes}m ${seconds}s' : '${seconds}s';

    // Queued-recordings count ("pending X/Y"): only meaningful once there is a
    // queue — a single unsynced recording is already named by the duration line.
    final backlog = provider.sessionTranscriptionBacklogCounts;
    final showBacklogCount = backlog.total >= 2 && backlog.pending >= 1;

    // The indicator names the worst outcome across the session's WALs so it
    // can say what happens next, instead of always claiming a healthy local
    // save next to a spinner that never resolves (#14473).
    final worst = worstSessionSyncState(unsyncedWals);
    final bool uploading =
        inFlightSeconds > 0 || unsyncedWals.any((w) => w.syncDisplayState == WalSyncDisplayState.syncing);
    final bool retrying = worst == WalSyncDisplayState.retrying;
    final bool failed = worst != null && _isTerminalWalState(worst);
    final bool retryable = worst != null && isRetryableSyncState(worst);

    final Color dotColor;
    final String text;
    if (failed) {
      dotColor = OmiColors.danger;
      text = retryable ? context.l10n.audioUploadFailedTapRetry(label) : context.l10n.audioUploadFailedKeptLocal(label);
    } else if (retrying) {
      dotColor = OmiColors.warning;
      text = context.l10n.audioUploadRetrying(label);
    } else if (uploading) {
      dotColor = OmiColors.success;
      text = context.l10n.uploadingAudioForTranscription(label);
    } else {
      dotColor = OmiColors.success;
      text = context.l10n.audioSavedLocally(label);
    }

    final indicator = Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.border, width: 0.5),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Text(
                text,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
              ),
              if (!failed && !retrying && uploading) ...[
                const SizedBox(width: 8),
                const OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textTertiary),
              ],
            ],
          ),
          // How many queued recordings are still waiting for transcription out
          // of the session's total, so a drain after an outage reads as progress.
          if (showBacklogCount) ...[
            const SizedBox(height: 4),
            Text(
              context.l10n.transcriptionsPendingFraction(backlog.pending, backlog.total),
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            ),
          ],
        ],
      ),
    );

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
        child: Semantics(
          liveRegion: true,
          button: retryable,
          child: retryable
              ? GestureDetector(onTap: () => provider.retryFailedSessionWalUploads(), child: indicator)
              : indicator,
        ),
      ),
    );
  }

  /// Terminal for automatic uploads: failed (retry budget spent, but a
  /// deliberate retry can still work), corrupted, or past the recovery window.
  bool _isTerminalWalState(WalSyncDisplayState state) =>
      state == WalSyncDisplayState.failed ||
      state == WalSyncDisplayState.corrupted ||
      state == WalSyncDisplayState.outsideRecoveryWindow ||
      state == WalSyncDisplayState.unsupportedAudio;
}
