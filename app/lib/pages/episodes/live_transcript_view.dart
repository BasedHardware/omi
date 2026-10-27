import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_capturing/capture_recovery_status.dart';
import 'package:omi/pages/conversation_capturing/widgets/speaker_suggestion_chip.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/episodes/live_preview_transcript.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_coverage.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/components/local_stt_recovery_notice.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/conversation_photo_image.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/widgets/photos_grid.dart';
import 'package:omi/widgets/speaker_label.dart';
import 'package:omi/widgets/speaker_label_badge.dart';
import 'package:omi/widgets/transcript.dart';

/// The live transcript: the capture's recovery and upload banners, then every line as it arrives,
/// photos in the timeline, speaker naming and Omi's speaker suggestions.
///
/// With an [episode] (the episodes overlay is on), it also draws the episode's moment dividers
/// with their short headings and, under the line they were heard in, the tasks and reminders Omi
/// captured, each with Undo ([onDismissItem]). Without one it is exactly today's live transcript.
class LiveTranscriptView extends StatefulWidget {
  const LiveTranscriptView({
    super.key,
    this.topConversationId,
    this.rejectSpeaker,
    this.episode,
    this.onDismissItem,
    this.jumpToLatestBottom = 84,
  });

  final String? topConversationId;
  final SpeakerRejectionCall? rejectSpeaker;
  final Episode? episode;
  final ValueChanged<EpisodeItem>? onDismissItem;

  /// Distance of the jump-to-latest button from the bottom safe area.
  final double jumpToLatestBottom;

  @override
  State<LiveTranscriptView> createState() => _LiveTranscriptViewState();
}

class _LiveTranscriptViewState extends State<LiveTranscriptView> {
  final TranscriptScrollStateStore _transcriptScrollStateStore = TranscriptScrollStateStore();
  bool _rejectingSuggestion = false;

  TranscriptScrollState _scrollStateFor(String sessionId) => _transcriptScrollStateStore.forSession(sessionId);

  // Memoized timeline derivations (see _buildChronologicalTimeline): the membership snapshot,
  // the speaker resolver, the episode decorations and the photo groups.
  int _timelineKey = -1;
  List<TranscriptSegment>? _timelineSegments;
  SpeakerNames? _timelineNames;
  LiveTranscriptDecorations? _timelineDecorations;
  List<ConversationPhoto>? _timelinePhotos;
  List<List<ConversationPhoto>>? _timelinePhotoGroups;

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        final connectivity = context.watch<ConnectivityProvider>();
        final usage = context.watch<UsageProvider>();
        final photoChannelActive = _photoChannelActive(deviceProvider.connectedDevice);
        final transcriptionInterrupted = provider.recordingState == RecordingState.interrupted;
        final transcriptSessionId =
            provider.activeCaptureSessionId ?? widget.topConversationId ?? 'pending-live-capture';
        final transcriptScrollState = _scrollStateFor(transcriptSessionId);
        final decorated = widget.episode != null;
        // Under the transcript on the episode page, as the last thing read; the legacy page's
        // floating controls cover its bottom, so there it stays on top.
        final behind = _showsLivePreview(provider)
            ? ListenableBuilder(
                listenable: provider.livePreview!,
                builder: (context, _) => _quietBehindLine(provider) ?? const SizedBox.shrink(),
              )
            : null;
        return Column(
          children: [
            const CaptureRecoveryStatus(),
            const HeldAudioLiveBanner(),
            if (provider.localSttFailure case final failure?)
              LocalSttRecoveryNotice(
                failure: failure,
                onRetry: provider.retryLocalTranscription,
                onSetup: () => routeToPage(context, const TranscriptionSettingsPage()),
              ),
            _buildUnsyncedWalIndicator(provider),
            if (behind != null && !decorated) behind,
            Expanded(
              child: _showsLivePreview(provider)
                  ? _previewBody(provider, transcriptSessionId, transcriptScrollState,
                      widget.topConversationId ?? provider.topConversationId)
                  : provider.segments.isEmpty && provider.photos.isEmpty
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
                      : provider.photos.isNotEmpty || decorated
                          ? _buildChronologicalTimeline(
                              provider,
                              transcriptSessionId,
                              transcriptScrollState,
                              widget.topConversationId ?? provider.topConversationId,
                            )
                          : getTranscriptWidget(
                              false,
                              List<TranscriptSegment>.of(provider.segments),
                              provider.photos,
                              deviceProvider.connectedDevice,
                              bottomMargin: 0,
                              taggingSegmentIds: provider.taggingSegmentIds,
                              transcriptKey: ValueKey('live-transcript-$transcriptSessionId'),
                              followLatest: true,
                              scrollState: transcriptScrollState,
                              jumpToLatestButtonBottom:
                                  MediaQuery.paddingOf(context).bottom + widget.jumpToLatestBottom,
                              contentVersion: provider.segmentsPhotosVersion,
                              editSegment: (segmentId, speakerId) => _nameSpeaker(segmentId, speakerId, provider),
                            ),
            ),
            if (behind != null && decorated) behind,
          ],
        );
      },
    );
  }

  /// The preview body of a local-preview session: the whole surface when no
  /// final line has arrived, else the final transcript with the "Live on this
  /// phone" divider and the uncovered preview lines under it.
  Widget _previewBody(
    CaptureProvider provider,
    String sessionId,
    TranscriptScrollState scrollState,
    String? conversationId,
  ) {
    final preview = provider.livePreview!;
    if (provider.segments.isEmpty) {
      return LivePreviewTranscript(preview: preview, bottomInset: widget.jumpToLatestBottom);
    }
    return ListenableBuilder(
      listenable: preview,
      builder: (context, _) => _buildChronologicalTimeline(
        provider,
        sessionId,
        scrollState,
        conversationId,
        preview: preview,
      ),
    );
  }

  /// Builds a chronological timeline interleaving photo groups and transcript segments, with the
  /// episode's moment dividers and captured items when there is an episode.
  Widget _buildChronologicalTimeline(
    CaptureProvider provider,
    String sessionId,
    TranscriptScrollState scrollState,
    String? conversationId, {
    LivePreviewController? preview,
  }) {
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    // The copy, the speaker resolver and the episode decorations walk every line, and a capture
    // notifies several times a minute while live; recompute only when the transcript, the
    // people list or the episode itself changed (the version covers photos too).
    final key = Object.hash(
      provider.segmentsPhotosVersion,
      provider.segments.length,
      identityHashCode(provider.segments),
      identityHashCode(provider.photos),
      identityHashCode(people),
      identityHashCode(widget.episode),
      conversationId,
    );
    if (_timelineKey != key) {
      _timelineKey = key;
      // A lazy row can be requested after a server deletion mutates the capture
      // list, while its old delegate still has the previous itemCount. Keep one
      // membership snapshot for that delegate, its names and decorations.
      _timelineSegments = List<TranscriptSegment>.of(provider.segments);
      _timelineNames =
          SpeakerNames.forSegments(_timelineSegments!, people: people, l10n: context.l10n, deferShortVoices: true);
      _timelineDecorations = LiveTranscriptDecorations.of(widget.episode, conversationId, _timelineSegments!);
      _timelinePhotos = List<ConversationPhoto>.from(provider.photos)
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt));

      // Group consecutive photos taken within 30 seconds of each other
      final List<List<ConversationPhoto>> photoGroups = [];
      if (_timelinePhotos!.isNotEmpty) {
        List<ConversationPhoto> currentGroup = [_timelinePhotos!.first];
        for (int i = 1; i < _timelinePhotos!.length; i++) {
          if (_timelinePhotos![i].createdAt.difference(_timelinePhotos![i - 1].createdAt).inSeconds <= 30) {
            currentGroup.add(_timelinePhotos![i]);
          } else {
            photoGroups.add(currentGroup);
            currentGroup = [_timelinePhotos![i]];
          }
        }
        photoGroups.add(currentGroup);
      }
      _timelinePhotoGroups = photoGroups;
    }
    final segments = _timelineSegments!;
    final names = _timelineNames!;
    final decorations = _timelineDecorations!;
    final photos = _timelinePhotos!;
    final photoGroups = _timelinePhotoGroups!;

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
      jumpToLatestButtonBottom: MediaQuery.paddingOf(context).bottom + widget.jumpToLatestBottom,
      contentVersion: provider.segmentsPhotosVersion ^
          decorations.signature ^
          (preview == null
              ? 0
              : Object.hash(preview.lines.length, preview.lines.lastOrNull?.id, preview.lines.lastOrNull?.text.length)),
      layoutIdentity: widget.episode == null ? 'photo-timeline' : 'episode-timeline',
      leadingItems: leadingItems,
      leadingItemIds: photoGroups.map((group) => group.first.id).toList(),
      segmentBuilder: (context, segment, index) {
        final line = _buildTranscriptTimelineItem(segment, provider, people, names);
        final divider = decorations.dividerBefore[segment.id];
        final items = decorations.itemsAfter[segment.id] ?? const <EpisodeItem>[];
        final tail = index == segments.length - 1 && preview != null
            ? LivePreviewTail(preview: preview, finalSegments: segments, finalOrigin: provider.liveTranscriptStartedAt)
            : null;
        if (divider == null && items.isEmpty && tail == null) return line;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (divider != null) EpisodeMomentDivider(moment: divider),
            line,
            for (final item in items) EpisodeCapturedItemCard(item: item, onUndo: widget.onDismissItem),
            if (tail != null) tail,
          ],
        );
      },
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
          Column(
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: OmiColors.surface2,
                child: Icon(Icons.camera_alt, size: 16, color: OmiColors.textSecondary),
              ),
              const SizedBox(height: 2),
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
                        Icon(Icons.camera_alt, size: 12, color: OmiColors.textTertiary),
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
        final saved = await provider.assignSpeakerToConversation(
          speakerId,
          personId,
          personName,
          segmentIds,
          applyToSpeaker: applyToSpeaker,
        );
        if (saved) {
          // The user's own answer now: no longer a label Omi carried over.
          for (final segment in provider.segments) {
            if (segmentIds.contains(segment.id) || (applyToSpeaker && segment.speakerId == speakerId)) {
              segment.speakerLabelSource = SpeakerLabelSource.manual;
            }
          }
          if (mounted) setState(() {});
        }
        return saved;
      },
    );
  }

  void _editSegmentSpeaker(TranscriptSegment segment, CaptureProvider provider) =>
      _nameSpeaker(segment.id, segment.speakerId, provider);

  /// "Someone Else…" on a suggestion is an answer too: tell Omi this voice is not that person,
  /// then let the user say who it is.
  Future<void> _rejectSuggestion(TranscriptSegment segment, Person person, CaptureProvider provider) async {
    if (_rejectingSuggestion) return;
    final conversationId = widget.topConversationId ?? provider.topConversationId;
    final sessionId = provider.activeCaptureSessionId;
    if (conversationId != null) {
      _rejectingSuggestion = true;
      try {
        final result = await (widget.rejectSpeaker ?? rejectConversationSpeaker)(
          conversationId,
          segment.speakerId,
          SpeakerRejection.notPerson,
          personId: person.id,
        );
        if (!mounted ||
            provider.activeCaptureSessionId != sessionId ||
            (widget.topConversationId ?? provider.topConversationId) != conversationId) {
          return;
        }
        if (result is! ApiSuccess<ServerConversation>) {
          OmiFeedback.error(context, context.l10n.speakerTagPromptAnswerFailed);
          return;
        }
      } catch (_) {
        if (mounted) OmiFeedback.error(context, context.l10n.speakerTagPromptAnswerFailed);
        return;
      } finally {
        _rejectingSuggestion = false;
      }
    }
    if (mounted) _editSegmentSpeaker(segment, provider);
  }

  /// A pinned near-miss the backend asked about for this unlabeled segment, if its person is known.
  Person? _pinnedSuggestion(TranscriptSegment segment, CaptureProvider provider, List<Person> people) {
    if (segment.isUser || segment.personId != null) return null;
    final suggestedId = provider.suggestionsBySegmentId[segment.id]?.suggestedPersonId;
    return suggestedId == null ? null : personById(people, suggestedId);
  }

  /// "Yes" on the inline suggestion labels every unlabeled line from this speaker.
  Future<void> _acceptSuggestion(TranscriptSegment segment, Person person, CaptureProvider provider) async {
    final ids = [
      for (final s in provider.segments)
        if (s.speakerId == segment.speakerId && !s.isUser && s.personId == null) s.id,
    ];
    OmiHaptics.light();
    final ok = await provider.assignSpeakerToConversation(
      segment.speakerId,
      person.id,
      person.name,
      ids,
      applyToSpeaker: true,
    );
    if (!mounted) return;
    ok ? OmiHaptics.success() : OmiFeedback.error(context, context.l10n.somethingWentWrongTryAgain);
  }

  Widget _buildTranscriptTimelineItem(
    TranscriptSegment segment,
    CaptureProvider provider,
    List<Person> people,
    SpeakerNames names,
  ) {
    final bool isUser = segment.isUser;
    final name = names.forSegment(segment, person: personById(people, segment.personId));
    Widget avatar() => Semantics(
          button: true,
          label: context.l10n.identifySpeaker,
          excludeSemantics: true,
          onTap: () => _editSegmentSpeaker(segment, provider),
          child: GestureDetector(
            onTap: () => _editSegmentSpeaker(segment, provider),
            child: Column(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: OmiColors.surface2,
                  child: Icon(Icons.person, size: 16, color: OmiColors.textSecondary),
                ),
                const SizedBox(height: 2),
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
          if (!isUser) ...[avatar(), const SizedBox(width: 8)],
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
                    if (!isUser &&
                        segment.speakerId != omiSpeakerId &&
                        (SpeakerLabelSource.isConfirmed(segment.speakerLabelSource) ||
                            segment.speakerLabelSource == SpeakerLabelSource.auto))
                      OmiButton.tertiary(
                        key: ValueKey('edit_speaker_label_${segment.id}'),
                        label: name,
                        leading: SpeakerLabelBadge(source: segment.speakerLabelSource),
                        size: OmiButtonSize.compact,
                        onPressed: () => _editSegmentSpeaker(segment, provider),
                      )
                    else
                      Text(name, style: OmiType.caption.copyWith(color: OmiColors.textSecondary)),
                    if (_pinnedSuggestion(segment, provider, people) case final suggested?)
                      SpeakerSuggestionChip(
                        key: ValueKey('suggestion_${segment.id}'),
                        person: suggested,
                        onYes: () => _acceptSuggestion(segment, suggested, provider),
                        onSomeoneElse: () => _rejectSuggestion(segment, suggested, provider),
                      ),
                    const SizedBox(height: 4),
                    Text(segment.text, style: OmiType.subhead.copyWith(height: 1.4)),
                  ],
                ),
              ),
            ),
          ),
          if (isUser) ...[const SizedBox(width: 8), avatar()],
        ],
      ),
    );
  }

  /// A local-preview session shows the on-device preview instead of the cloud
  /// transcript. Cloud lines can still arrive (phone-mic capture, or audio the
  /// batch journal refused); they keep today's view only when this phone has
  /// no preview engine, and a photo timeline always keeps today's view.
  bool _showsLivePreview(CaptureProvider provider) {
    final preview = provider.livePreview;
    if (preview == null || !provider.localPreviewAdmitted || !preview.admitted) return false;
    if (!provider.pendantCaptureVerified || provider.photos.isNotEmpty) return false;
    return provider.segments.isEmpty || preview.phase != LivePreviewPhase.unavailable;
  }

  /// Photos reach a live conversation only through camera-capable wearables
  /// (Ray-Ban Meta, OpenGlass). A phone-mic session has no photo channel, so
  /// its empty state must not promise one (#14473).
  bool _photoChannelActive(BtDevice? connectedDevice) {
    final type = connectedDevice?.type;
    return type == DeviceType.raybanMeta || type == DeviceType.openglass;
  }

  /// The live-capture empty state names only what this session can actually
  /// produce. A transcription outage is stated once, by the recovery banner
  /// (and the LocalSttRecoveryNotice, whose buttons are the point of it): an
  /// out-of-credits plan, a terminal STT failure and a local STT failure all
  /// get the truthful unavailable line here instead of copy that promises a
  /// transcript while none can appear (#14473). An offline device is waiting
  /// on the network, and `interrupted` means the transcription socket dropped
  /// and is reconnecting.
  String _liveCaptureEmptyStateText(
    CaptureProvider provider, {
    required ConnectivityProvider connectivity,
    required UsageProvider usage,
    required bool photoChannelActive,
    required bool transcriptionInterrupted,
  }) {
    if (!provider.pendantCaptureVerified) return '';
    if (provider.localSttFailure != null) return context.l10n.transcriptionUnavailableRecordingSaved;
    if (usage.isOutOfCredits) return context.l10n.transcriptionUnavailableRecordingSaved;
    if (provider.terminalTranscriptionFailure != null) {
      return context.l10n.transcriptionUnavailableRecordingContinues;
    }
    if (!connectivity.isConnected) return context.l10n.recordingOfflineTranscriptWillCatchUp;
    if (transcriptionInterrupted) return context.l10n.transcriptionPausedReconnecting;
    if (!photoChannelActive) return context.l10n.listeningTranscriptWillAppear;
    return context.l10n.waitingForTranscriptOrPhotos;
  }

  /// A local-preview session has no uploading pill to watch: one quiet line under the
  /// transcript says how far behind the final transcript is. Failures and retries keep
  /// today's actionable pill above it (its retry is the point of it). Null when the pill applies.
  Widget? _quietBehindLine(CaptureProvider provider) {
    if (!_showsLivePreview(provider)) return null;
    final unsyncedWals = provider.unsyncedSessionWals;
    final totalSeconds = unsyncedWals.fold<int>(0, (sum, w) => sum + w.seconds) + provider.inFlightAudioSeconds;
    // Uploaded audio has no pending-upload duration, but the server may still
    // be transcribing it. Only uncovered preview text proves we are waiting.
    final waitingWithoutDuration = totalSeconds == 0 &&
        LivePreviewCoverage.uncovered(
          provider.livePreview!.lines,
          provider.segments,
          provider.liveTranscriptStartedAt,
        ).isNotEmpty;
    if (totalSeconds <= 5 && !waitingWithoutDuration) return null;
    final worst = worstSessionSyncState(unsyncedWals);
    if ((worst != null && _isTerminalWalState(worst)) || worst == WalSyncDisplayState.retrying) return null;
    final l10n = context.l10n;
    final behind = (totalSeconds / 10).round() * 10;
    return SafeArea(
      top: false,
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.sm),
        child: Row(
          key: const Key('live_preview_behind_line'),
          children: [
            Icon(Icons.schedule, size: 14, color: OmiColors.textTertiary),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                behind > 0 ? l10n.livePreviewBehind(OmiDuration.compact(behind, l10n)) : l10n.livePreviewCatchingUp,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUnsyncedWalIndicator(CaptureProvider provider) {
    final unsyncedWals = provider.unsyncedSessionWals;
    final inFlightSeconds = provider.inFlightAudioSeconds;
    final totalSeconds = unsyncedWals.fold<int>(0, (sum, w) => sum + w.seconds) + inFlightSeconds;
    if (totalSeconds <= 5) return const SizedBox.shrink();

    if (_quietBehindLine(provider) != null) return const SizedBox.shrink();
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    final label = minutes > 0 ? '${minutes}m ${seconds}s' : '${seconds}s';

    // Count only missing chunks. The session total includes already synced chunks and
    // is not a queue length or a count of server transcription jobs.
    final backlog = provider.sessionTranscriptionBacklogCounts;
    final showBacklogCount = backlog.pending >= 1;

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
                OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textTertiary),
              ],
            ],
          ),
          // Missing phone WAL chunks; the session total also includes already synced audio.
          if (showBacklogCount) ...[
            const SizedBox(height: 4),
            Text(
              context.l10n.captureChunksPending(backlog.pending),
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
      state == WalSyncDisplayState.unsupportedAudio ||
      state == WalSyncDisplayState.uploadRejected;
}

/// Where the episode's moments and captured items sit in the live conversation's transcript.
class LiveTranscriptDecorations {
  const LiveTranscriptDecorations({required this.dividerBefore, required this.itemsAfter, required this.signature});

  /// A moment's divider goes above the first line it covers.
  final Map<String, EpisodeMoment> dividerBefore;

  /// A captured item goes under the line it was heard in.
  final Map<String, List<EpisodeItem>> itemsAfter;

  /// Changes whenever the decorations do, so the transcript list repaints them.
  final int signature;

  static const empty = LiveTranscriptDecorations(dividerBefore: {}, itemsAfter: {}, signature: 0);

  static LiveTranscriptDecorations of(Episode? episode, String? conversationId, List<TranscriptSegment> segments) {
    if (episode == null || conversationId == null || segments.isEmpty) return empty;
    final dividers = <String, EpisodeMoment>{};
    final moments = [
      for (final m in episode.moments)
        if (m.conversationId == conversationId && m.heading.isNotEmpty) m,
    ]..sort((a, b) => a.startOffset.compareTo(b.startOffset));
    for (final moment in moments) {
      final first = segments.where((s) => s.end > moment.startOffset).firstOrNull;
      if (first != null) dividers.putIfAbsent(first.id, () => moment);
    }
    final items = <String, List<EpisodeItem>>{};
    for (final item in episode.items) {
      final offset = item.segmentOffset;
      if (!item.visible || item.conversationId != conversationId || offset == null) {
        continue;
      }
      final line = segments.lastWhere((s) => s.start <= offset, orElse: () => segments.last);
      items.putIfAbsent(line.id, () => []).add(item);
    }
    return LiveTranscriptDecorations(
      dividerBefore: dividers,
      itemsAfter: items,
      signature: Object.hash(Object.hashAll(dividers.keys), Object.hashAll(episode.items.map((i) => (i.id, i.status)))),
    );
  }
}

/// The thin hairline that names where the final transcript ends and the
/// on-device preview continues.
class LivePreviewDivider extends StatelessWidget {
  const LivePreviewDivider({super.key});

  @override
  Widget build(BuildContext context) {
    final label = context.l10n.livePreviewOnPhoneDivider;
    final line = Expanded(child: Container(height: 1, color: OmiColors.surface2));
    return Semantics(
      header: true,
      label: label,
      excludeSemantics: true,
      child: Padding(
        key: const Key('live_preview_divider'),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xs),
        child: Row(
          children: [
            line,
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
              child: Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ),
            line,
          ],
        ),
      ),
    );
  }
}

/// Under the divider: the preview lines the final transcript does not already
/// cover — the recognizer's still-volatile newest words in lighter text. The
/// preview carries audio timestamps; only full interval coverage replaces a line.
class LivePreviewTail extends StatelessWidget {
  const LivePreviewTail({super.key, required this.preview, required this.finalSegments, required this.finalOrigin});

  final LivePreviewController preview;
  final List<TranscriptSegment> finalSegments;

  final DateTime? finalOrigin;

  @override
  Widget build(BuildContext context) {
    final lines = LivePreviewCoverage.uncovered(preview.lines, finalSegments, finalOrigin);
    if (lines.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        const LivePreviewDivider(),
        for (var i = 0; i < lines.length; i++)
          Padding(
            key: ValueKey('live_preview_tail_${lines[i].id}'),
            padding: EdgeInsets.fromLTRB(OmiSpacing.md, i == 0 ? OmiSpacing.xs : 0, OmiSpacing.md, OmiSpacing.sm),
            child: Text(
              lines[i].text,
              style: OmiType.body.copyWith(
                height: 1.4,
                color: lines[i].isFinal ? OmiColors.textPrimary : OmiColors.textSecondary,
              ),
            ),
          ),
        SizedBox(height: MediaQuery.paddingOf(context).bottom + 84),
      ],
    );
  }
}

/// "10:51 · Git support idea" between hairlines: where a moment of the episode begins.
class EpisodeMomentDivider extends StatelessWidget {
  const EpisodeMomentDivider({super.key, required this.moment});

  final EpisodeMoment moment;

  @override
  Widget build(BuildContext context) {
    final label = '${OmiDateFormat.of(context).time(moment.startedAt)} · ${moment.heading}';
    final line = Expanded(child: Container(height: 1, color: OmiColors.surface2));
    return Semantics(
      header: true,
      label: label,
      excludeSemantics: true,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xs),
        child: Row(
          children: [
            line,
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
              child: Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ),
            line,
          ],
        ),
      ),
    );
  }
}

/// A task or reminder Omi heard, under the line it was heard in. Provisional items carry Undo;
/// once the conversation's processing saved it, it says so.
class EpisodeCapturedItemCard extends StatelessWidget {
  const EpisodeCapturedItemCard({super.key, required this.item, this.onUndo});

  final EpisodeItem item;
  final ValueChanged<EpisodeItem>? onUndo;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final saved = item.status == EpisodeItemStatus.kept;
    final text = saved
        ? l10n.episodeTaskSaved(item.text)
        : item.isReminder
            ? l10n.episodeReminderCaptured(item.text)
            : l10n.episodeTaskCaptured(item.text);
    return Padding(
      key: ValueKey('episode_item_${item.id}'),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.xxs),
      child: Container(
        constraints: const BoxConstraints(minHeight: 44),
        padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.sm, OmiSpacing.xxs, OmiSpacing.xxs, OmiSpacing.xxs),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
        child: Row(
          children: [
            Icon(
              saved ? Icons.check_circle_rounded : (item.isReminder ? Icons.alarm_rounded : Icons.check_circle_outline),
              size: 18,
              color: saved ? OmiColors.textPrimary : OmiColors.textSecondary,
            ),
            const SizedBox(width: OmiSpacing.xs),
            Expanded(child: Text(text, style: OmiType.footnote)),
            if (!saved && onUndo != null)
              OmiButton.tertiary(
                key: ValueKey('episode_item_undo_${item.id}'),
                label: l10n.undo,
                size: OmiButtonSize.compact,
                onPressed: () {
                  OmiHaptics.light();
                  onUndo!(item);
                },
              ),
          ],
        ),
      ),
    );
  }
}
