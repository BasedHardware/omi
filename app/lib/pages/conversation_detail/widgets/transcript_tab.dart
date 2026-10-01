import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart' show assignBulkConversationTranscriptSegments;
import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/earlier_voice_matches_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/edit_segment_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_summary_action.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:omi/widgets/extensions/string.dart';

/// The conversation detail's Transcript tab: the speaker-summary action, then the transcript (or
/// the imported text of an external conversation), with segment editing and speaker naming.
class TranscriptWidgets extends StatefulWidget {
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;
  final Function(TranscriptSegment)? onSegmentTap;

  const TranscriptWidgets({
    super.key,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onTapWhenSearchEmpty,
    this.onSegmentTap,
  });

  @override
  State<TranscriptWidgets> createState() => _TranscriptWidgetsState();
}

class _TranscriptWidgetsState extends State<TranscriptWidgets> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  /// Follows a tag to its outcome (voice learned or not). Tests and the visual audit provide one
  /// seeded with fake fetchers; the app creates its own.
  SpeakerTagOutcomeController? _ownOutcome;
  late final SpeakerTagOutcomeController _outcome =
      context.read<SpeakerTagOutcomeController?>() ?? (_ownOutcome = SpeakerTagOutcomeController());

  @override
  void dispose() {
    _ownOutcome?.dispose();
    super.dispose();
  }

  void _dismissSearchIfEmpty() {
    FocusScope.of(context).unfocus();
    if (widget.searchQuery.isEmpty) widget.onTapWhenSearchEmpty?.call();
  }

  bool _requireConnection() {
    if (Provider.of<ConnectivityProvider>(context, listen: false).isConnected) return true;
    ConnectivityProvider.showNoInternetDialog(context);
    return false;
  }

  void _editSegmentText(ConversationDetailProvider provider, int segmentIndex) {
    if (!_requireConnection()) return;
    final segments = provider.conversation.transcriptSegments;
    final segment = segments[segmentIndex];
    final people = context.read<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final speakerName = SpeakerNames.forSegments(
      segments,
      people: people,
      l10n: context.l10n,
    ).forSegment(segment);
    PlatformManager.instance.analytics.editSegmentTextStarted();
    bool saved = false;
    showEditSegmentBottomSheet(
      context,
      segment: segment,
      speakerName: speakerName,
      onSave: (newText) {
        saved = true;
        PlatformManager.instance.analytics.editSegmentTextSaved();
        provider.saveEditingSegmentText(segmentIndex, newText);
      },
      onDismissed: () {
        if (!saved) PlatformManager.instance.analytics.editSegmentTextCancelled();
      },
    );
  }

  void _nameSpeaker(
    ConversationDetailProvider provider,
    String segmentId,
    int speakerId,
  ) {
    if (!_requireConnection()) return;
    showNameSpeakerSheet(
      context,
      speakerId: speakerId,
      segmentId: segmentId,
      segments: provider.conversation.transcriptSegments,
      onSpeakerAssigned: (speakerId, personId, personName, segmentIds, applyToSpeaker) async {
        return _startSpeakerAssignment(
          provider,
          provider.conversation.id,
          speakerId,
          personId,
          personName,
          segmentIds,
          applyToSpeaker,
        );
      },
      onSpeakerRejected: (kind) async {
        final segment = provider.conversation.transcriptSegments.where((s) => s.id == segmentId).firstOrNull;
        return segment != null && await provider.rejectSpeakerLabel(segment, kind);
      },
    );
  }

  /// "Yes" under a line Omi named by voice: the user's answer for every line from that voice.
  void _confirmSpeakerLabel(ConversationDetailProvider provider, TranscriptSegment segment) {
    final personId = segment.personId;
    if (personId == null || !_requireConnection()) return;
    final name = context.read<PeopleProvider>().people.where((p) => p.id == personId).firstOrNull?.name ?? '';
    OmiHaptics.light();
    _startSpeakerAssignment(provider, provider.conversation.id, segment.speakerId, personId, name, [segment.id], true);
  }

  /// "Not <name>": clears that label from the voice and tells Omi not to match it that way again.
  Future<void> _rejectSpeakerLabel(ConversationDetailProvider provider, TranscriptSegment segment) async {
    if (!_requireConnection()) return;
    OmiHaptics.light();
    final rejected = await provider.rejectSpeakerLabel(segment, SpeakerRejection.notPerson);
    if (!mounted) return;
    rejected
        ? OmiFeedback.confirm(context, context.l10n.speakerTagPromptRejectedToast)
        : OmiFeedback.error(context, context.l10n.failedToSaveCheckConnection);
  }

  void _reviewEarlierMatches(SpeakerTagOutcome outcome) {
    showEarlierVoiceMatchesSheet(
      context,
      personName: outcome.personName,
      matches: outcome.matches,
      onAnswer: (match, same) async {
        final saved = same
            ? await assignBulkConversationTranscriptSegments(
                match.conversationId,
                match.segmentIds,
                personId: outcome.personId,
                speakerId: match.speakerId,
              )
            : await rejectConversationSpeaker(
                match.conversationId,
                match.speakerId,
                SpeakerRejection.notPerson,
                personId: outcome.personId,
              ) is ApiSuccess<void>;
        if (saved) _outcome.removeMatch(match);
        return saved;
      },
    );
  }

  bool _startSpeakerAssignment(
    ConversationDetailProvider provider,
    String conversationId,
    int speakerId,
    String personId,
    String personName,
    List<String> segmentIds,
    bool applyToSpeaker,
  ) {
    final peopleProvider = context.read<PeopleProvider>();
    final newPerson = personId.isEmpty;
    final temporaryId = newPerson ? 'optimistic-person:${DateTime.now().microsecondsSinceEpoch}' : null;
    if (temporaryId != null) {
      peopleProvider.addOptimisticPerson(
        Person(
          id: temporaryId,
          name: personName,
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );
    }
    var resolvedId = personId;
    final pending = provider.startSpeakerAssignment(
      segmentIds,
      temporaryId ?? personId,
      speakerId: applyToSpeaker ? speakerId : null,
      expectedConversationId: conversationId,
      createPerson: newPerson ? () async => (await peopleProvider.createPersonProvider(personName))?.id : null,
      onReconciled: (id) {
        resolvedId = id;
        if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
      },
      onFailed: () {
        if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
        if (!mounted) return;
        OmiFeedback.error(
          context,
          context.l10n.failedToSaveCheckConnection,
          actionLabel: context.l10n.retry,
          onAction: () => _startSpeakerAssignment(
            provider,
            conversationId,
            speakerId,
            resolvedId,
            personName,
            segmentIds,
            applyToSpeaker,
          ),
        );
      },
    );
    if (pending == null) {
      if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
      return false;
    }
    final linesLabeled = applyToSpeaker
        ? provider.conversation.transcriptSegments.where((s) => s.speakerId == speakerId).length
        : segmentIds.length;
    unawaited(
      pending.then((saved) {
        if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
        if (saved) {
          PlatformManager.instance.analytics.taggedSegment(
            resolvedId == 'user' ? 'User' : 'User Person',
          );
          if (resolvedId != 'user' && identical(provider.conversationOrNull?.id, conversationId)) {
            _outcome.follow(personId: resolvedId, personName: personName, linesLabeled: linesLabeled);
          }
        }
      }),
    );
    return true;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Listener(
      onPointerDown: (_) => _dismissSearchIfEmpty(),
      child: GestureDetector(
        excludeFromSemantics: true,
        behavior: HitTestBehavior.translucent,
        onTap: _dismissSearchIfEmpty,
        child: Consumer<ConversationDetailProvider>(
          builder: (context, provider, child) {
            final conversation = provider.conversation;
            final segments = conversation.transcriptSegments;
            final photos = conversation.photos;

            if (segments.isEmpty && photos.isEmpty) {
              return Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xxl),
                child: ExpandableTextWidget(
                  text: (conversation.externalIntegration?.text ?? '').decodeString,
                  maxLines: 1000,
                  linkColor: OmiColors.textSecondary,
                  style: OmiType.subhead.copyWith(
                    color: OmiColors.textSecondary,
                    height: 1.3,
                  ),
                  toggleExpand: provider.toggleIsTranscriptExpanded,
                  isExpanded: provider.isTranscriptExpanded,
                ),
              );
            }

            return Column(
              children: [
                SpeakerSummaryAction(provider: provider),
                ListenableBuilder(
                  listenable: _outcome,
                  builder: (context, _) {
                    final outcome = _outcome.outcome;
                    if (outcome == null) return const SizedBox.shrink();
                    return SpeakerTagOutcomeCard(
                      outcome: outcome,
                      onClose: _outcome.dismiss,
                      onReview: () => _reviewEarlierMatches(outcome),
                    );
                  },
                ),
                Expanded(
                  child: getTranscriptWidget(
                    false,
                    segments,
                    photos,
                    null,
                    conversationId: conversation.id,
                    horizontalMargin: false,
                    topMargin: false,
                    canDisplaySeconds: provider.canDisplaySeconds,
                    isConversationDetail: true,
                    unresolvedSpeakers: conversation.speakerResolution?.status == 'unavailable',
                    bottomMargin: 150,
                    searchQuery: widget.searchQuery,
                    currentResultIndex: widget.currentResultIndex,
                    onTapWhenSearchEmpty: widget.onTapWhenSearchEmpty,
                    onSegmentTap: widget.onSegmentTap,
                    onEditSegmentText: (segmentIndex) => _editSegmentText(provider, segmentIndex),
                    editSegment: (segmentId, speakerId) => _nameSpeaker(provider, segmentId, speakerId),
                    onConfirmSpeakerLabel: (segment) => _confirmSpeakerLabel(provider, segment),
                    onRejectSpeakerLabel: (segment) => _rejectSpeakerLabel(provider, segment),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
