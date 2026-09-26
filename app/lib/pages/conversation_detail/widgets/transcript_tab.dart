import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/edit_segment_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_summary_action.dart';
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
    unawaited(
      pending.then((saved) {
        if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
        if (saved) {
          PlatformManager.instance.analytics.taggedSegment(
            resolvedId == 'user' ? 'User' : 'User Person',
          );
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
            if (provider.loadingReprocessTranscription &&
                provider.reprocessConversationId == provider.conversation.id) {
              return Padding(
                padding: const EdgeInsets.only(top: 18.0),
                child: OmiLoadingState(label: context.l10n.retranscribingConversation),
              );
            }

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
                    bottomMargin: 150,
                    searchQuery: widget.searchQuery,
                    currentResultIndex: widget.currentResultIndex,
                    onTapWhenSearchEmpty: widget.onTapWhenSearchEmpty,
                    onSegmentTap: widget.onSegmentTap,
                    onEditSegmentText: (segmentIndex) => _editSegmentText(provider, segmentIndex),
                    editSegment: (segmentId, speakerId) => _nameSpeaker(provider, segmentId, speakerId),
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
