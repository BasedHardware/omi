import 'dart:async';

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
import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/widgets/speaker_label_badge.dart';
import 'widgets/carried_speaker_banner.dart';
import 'widgets/speaker_suggestion_chip.dart';

/// Switch the home IndexedStack to Home (the conversation list) *before* popping the capturing
/// route so the user lands there with no flash of the previous page.
void switchHomeToConversationsTab(BuildContext context) {
  context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
}

class ConversationCapturingPage extends StatefulWidget {
  final String? topConversationId;

  final SpeakerRejectionCall? rejectSpeaker;

  const ConversationCapturingPage({super.key, this.topConversationId, this.rejectSpeaker});

  @override
  State<ConversationCapturingPage> createState() => _ConversationCapturingPageState();
}

class _ConversationCapturingPageState extends State<ConversationCapturingPage> {
  /// Room under the transcript card for the floating dock: the Scaffold's margin above the bottom
  /// inset, the dock (a regular button in its padding) and a gap to the card.
  static const double _dockClearance = kFloatingActionButtonMargin + 48 + OmiSpacing.xs * 2 + OmiSpacing.md;

  final TranscriptScrollStateStore _transcriptScrollStateStore = TranscriptScrollStateStore();

  final scaffoldKey = GlobalKey<ScaffoldState>();
  bool _mutePending = false;
  bool _rejectingSuggestion = false;
  final Set<String> _closedCarriedSpeakers = {};

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
        if (phone && !provider.isPaused) PlatformManager.instance.analytics.phoneMicRecordingStarted();
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
    // A swipe back during the finish has already popped this route; it only stays mounted while it
    // animates out, and a pop then would take Home with it and leave the navigator empty.
    final route = ModalRoute.of(context);
    if (route != null && route.isCurrent) Navigator.of(context).pop();
  }

  /// The live page's state, resolved exactly as the Home capture card resolves it
  /// (`captureInterruption` + `liveCaptureDisplayState`): the OS holding the mic, a mute or a call
  /// is Paused, capture recovering on its own (a dropped socket, a mic stall) is Reconnecting, a
  /// terminal transcription failure or offline buffering is named as such, otherwise Listening.
  CaptureDisplayState _displayState(CaptureProvider provider, {required bool capturingPhotos}) {
    final interruption = captureInterruption(
      interrupted: provider.recordingState == RecordingState.interrupted,
      readerPaused: provider.isPaused,
      osHoldsMic: provider.isCallActive,
    );
    return liveCaptureDisplayState(
      audioInterrupted: interruption == CaptureInterruption.micTaken,
      reconnecting: interruption == CaptureInterruption.recovering,
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
        final state = _displayState(provider, capturingPhotos: provider.photos.isNotEmpty);
        final live = state == CaptureDisplayState.listening ||
            state == CaptureDisplayState.capturing ||
            state == CaptureDisplayState.recording;
        return Scaffold(
          key: scaffoldKey,
          backgroundColor: OmiColors.surface0,
          appBar: ConversationStateAppBar(
            title: context.l10n.liveTranscript,
            startedAt: provider.liveCaptureStartedAt,
            showStatus: effectivelyMuted || provider.pendantCaptureVerified,
            state: state,
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
              ..._buildCarriedSpeakerBanner(provider),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.fromLTRB(
                    OmiSpacing.sm,
                    OmiSpacing.xs,
                    OmiSpacing.sm,
                    MediaQuery.paddingOf(context).bottom + _dockClearance,
                  ),
                  child: _TranscriptCard(
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
                        : _buildTranscript(
                            provider,
                            transcriptSessionId,
                            transcriptScrollState,
                            widget.topConversationId ?? provider.topConversationId,
                            live: live,
                          ),
                  ),
                ),
              ),
            ],
          ),
          floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
          // Pause/Resume (a pause glyph: mics belong to Ask Omi) and Finish, the one stop, side by
          // side in a dock.
          floatingActionButton:
              (provider.liveCaptureSource != null || provider.segments.isNotEmpty || provider.photos.isNotEmpty)
                  ? _Dock(
                      children: [
                        if (provider.liveCaptureSource != null &&
                            LiveCaptureCard.canPause(provider.recordingDevice, source: provider.liveCaptureSource)) ...[
                          OmiButton(
                            key: const Key('capture_pause_button'),
                            label: effectivelyMuted ? context.l10n.resume : context.l10n.pause,
                            leading: Icon(effectivelyMuted ? Icons.play_arrow_rounded : Icons.pause_rounded),
                            pill: true,
                            onPressed: _mutePending || provider.isCallActive ? null : () => _toggleMute(provider),
                          ),
                          const SizedBox(width: OmiSpacing.xs),
                        ],
                        OmiButton.secondary(
                          key: const Key('process_now_button'),
                          label: context.l10n.finish,
                          leading: const Icon(Icons.check_rounded),
                          pill: true,
                          onPressed: () => _stopConversation(provider),
                        ),
                      ],
                    )
                  : null,
        );
      },
    );
  }

  /// The transcript list: a camera-capable device's photo groups first, in time order, then every
  /// line, each built by [_buildTranscriptLine]. [live] marks the newest line with a caret.
  Widget _buildTranscript(
    CaptureProvider provider,
    String sessionId,
    TranscriptScrollState scrollState,
    String? conversationId, {
    required bool live,
  }) {
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
      separator: false,
      canDisplaySeconds: false,
      // The list keeps 120 pt of slack under its last line for a page's floating controls. Here
      // they sit below the card, so only the card's own padding is left.
      bottomMargin: OmiSpacing.lg - 120,
      followLatest: true,
      scrollState: scrollState,
      jumpToLatestButtonBottom: OmiSpacing.md,
      contentVersion: provider.segmentsPhotosVersion,
      layoutIdentity: photoGroups.isEmpty ? 'live-transcript' : 'photo-timeline',
      leadingItems: leadingItems,
      leadingItemIds: photoGroups.map((group) => group.first.id).toList(),
      segmentBuilder: (context, segment, index) =>
          _buildTranscriptLine(segment, index, provider, people, names, live: live),
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

  /// The first label Omi carried into this conversation from the user's answer earlier in the
  /// same recording, until the user changes it or closes the note.
  List<Widget> _buildCarriedSpeakerBanner(CaptureProvider provider) {
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    for (final segment in carriedSpeakerSegments(provider.segments)) {
      final key = '${segment.speakerId}:${segment.personId}';
      final person = personById(people, segment.personId);
      if (person == null || _closedCarriedSpeakers.contains(key)) continue;
      return [
        CarriedSpeakerBanner(
          name: person.name,
          onChange: () => _editSegmentSpeaker(segment, provider),
          onClose: () => setState(() => _closedCarriedSpeakers.add(key)),
        ),
      ];
    }
    return const [];
  }

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
            (widget.topConversationId ?? provider.topConversationId) != conversationId) return;
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

  /// One line of the live transcript: the speaker's name in small type above the words (You, the
  /// person once named, otherwise Speaker N), then the words. Tapping the line names the speaker.
  /// The newest line is full ink and carries a caret while [live]; earlier lines step back to
  /// secondary. A named speaker's label badge, the tagging spinner, the likely-speaker chip and
  /// translations keep their places from the saved transcript.
  Widget _buildTranscriptLine(
    TranscriptSegment segment,
    int index,
    CaptureProvider provider,
    List<Person> people,
    SpeakerNames names, {
    required bool live,
  }) {
    final person = personById(people, segment.personId);
    final name = names.forSegment(segment, person: person);
    final isTagging = provider.taggingSegmentIds.contains(segment.id);
    final previous = index > 0 ? provider.segments[index - 1] : null;
    // The badge marks the start of a speaker's turn, not every line of it.
    final startsTurn = previous == null ||
        previous.isUser != segment.isUser ||
        previous.speakerId != segment.speakerId ||
        previous.personId != segment.personId ||
        previous.speakerLabelSource != segment.speakerLabelSource;
    final latest = index == provider.segments.length - 1;
    final words = OmiType.title3.copyWith(
      fontWeight: FontWeight.w400,
      height: 1.4,
      color: latest ? OmiColors.textPrimary : OmiColors.textSecondary,
    );
    final suggested = _pinnedSuggestion(segment, provider, people);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      excludeFromSemantics: true,
      onTap: () => _editSegmentSpeaker(segment, provider),
      child: Padding(
        padding: EdgeInsets.only(top: index == 0 ? 0 : OmiSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              button: true,
              label: name,
              hint: context.l10n.identifySpeaker,
              excludeSemantics: true,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    name,
                    style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w500),
                  ),
                  if (startsTurn && person != null && !isTagging) ...[
                    const SizedBox(width: OmiSpacing.xxs),
                    SpeakerLabelBadge(source: segment.speakerLabelSource),
                  ],
                  if (isTagging) ...[
                    const SizedBox(width: OmiSpacing.xs),
                    const OmiSpinner(size: OmiSpinnerSize.small),
                  ],
                ],
              ),
            ),
            if (suggested != null)
              SpeakerSuggestionChip(
                key: ValueKey('suggestion_${segment.id}'),
                person: suggested,
                onYes: () => _acceptSuggestion(segment, suggested, provider),
                onSomeoneElse: () => _rejectSuggestion(segment, suggested, provider),
              ),
            const SizedBox(height: OmiSpacing.xxs),
            Text.rich(
              TextSpan(
                text: tryDecodingText(segment.text),
                children: [
                  if (live && latest)
                    WidgetSpan(
                      alignment: PlaceholderAlignment.middle,
                      child: Padding(
                        padding: const EdgeInsetsDirectional.only(start: OmiSpacing.xxs),
                        child: ExcludeSemantics(
                          child: Container(width: 2, height: words.fontSize, color: OmiColors.textPrimary),
                        ),
                      ),
                    ),
                ],
              ),
              style: words,
            ),
            if (segment.translations.isNotEmpty) ...[
              for (final translation in segment.translations)
                Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.xxs),
                  child: Text(
                    tryDecodingText(translation.text),
                    style: OmiType.footnote.copyWith(
                      color: OmiColors.textSecondary,
                      fontStyle: FontStyle.italic,
                      height: 1.3,
                    ),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xxs),
                child: Semantics(
                  button: true,
                  child: GestureDetector(
                    onTap: () => showOmiAlert(
                      context,
                      title: context.l10n.translationNotice,
                      message: context.l10n.translationNoticeMessage,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.check_circle, size: 12, color: OmiColors.textTertiary),
                        const SizedBox(width: OmiSpacing.xxs),
                        Text(
                          context.l10n.translatedByOmi,
                          style: OmiType.caption.copyWith(color: OmiColors.textTertiary, fontStyle: FontStyle.italic),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
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
    if (!provider.pendantCaptureVerified) return '';
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
                OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textTertiary),
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
      state == WalSyncDisplayState.unsupportedAudio ||
      state == WalSyncDisplayState.uploadRejected;
}

/// The transcript's card on the grouped page: surface1, a hairline and a little lift. The list
/// inside is clipped to the corners, and a fade at the top lets the oldest lines slip under the
/// edge instead of being cut.
class _TranscriptCard extends StatelessWidget {
  const _TranscriptCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final fill = OmiColors.surface1;
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: fill,
        borderRadius: OmiRadius.xlAll,
        border: Border.all(color: OmiColors.border, width: 0.5),
        boxShadow: OmiGlass.shadows,
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: Padding(padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg), child: child),
          ),
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            height: OmiSpacing.xxl,
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [fill, fill.withValues(alpha: 0)],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The live page's controls in one floating dock: Pause/Resume and Finish as labelled capsules on
/// a surface1 pill with the float shadow.
class _Dock extends StatelessWidget {
  const _Dock({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.xs),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.pillAll,
        boxShadow: OmiGlass.floatShadows,
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: children),
    );
  }
}
