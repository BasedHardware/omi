import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/speaker_labels.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What tagging a person came to: how many lines got the name, whether Omi learned the voice, and
/// whether the same voice is waiting in earlier conversations.
class SpeakerTagOutcome {
  const SpeakerTagOutcome({
    required this.personId,
    required this.personName,
    required this.linesLabeled,
    this.voiceState = 'pending',
    this.matches = const [],
  });

  final String personId;
  final String personName;
  final int linesLabeled;

  /// The server's `voice_learning_state`, or `pending` while it is still being read.
  final String voiceState;
  final List<api.PersonVoiceMatch> matches;

  bool get isSettled => voiceState != 'pending';

  SpeakerTagOutcome copyWith({String? voiceState, List<api.PersonVoiceMatch>? matches}) => SpeakerTagOutcome(
        personId: personId,
        personName: personName,
        linesLabeled: linesLabeled,
        voiceState: voiceState ?? this.voiceState,
        matches: matches ?? this.matches,
      );
}

typedef PersonFetcher = Future<ApiResult<Person>> Function(String personId);
typedef VoiceMatchesFetcher = Future<ApiResult<List<api.PersonVoiceMatch>>> Function(String personId);

/// Follows one tag until the server says what teaching the voice came to. Teaching runs after the
/// label is saved, so the person is re-read a few times; a tag that is still pending when the
/// reads run out is shown as "not learned yet" (the server retries when the conversation ends).
class SpeakerTagOutcomeController extends ChangeNotifier {
  SpeakerTagOutcomeController({
    PersonFetcher? fetchPerson,
    VoiceMatchesFetcher? fetchMatches,
    this.pollInterval = const Duration(seconds: 2),
    this.maxPolls = 6,
  })  : _fetchPerson = fetchPerson ?? api.getPerson,
        _fetchMatches = fetchMatches ?? api.getPersonVoiceMatches;

  final PersonFetcher _fetchPerson;
  final VoiceMatchesFetcher _fetchMatches;
  final Duration pollInterval;
  final int maxPolls;

  SpeakerTagOutcome? _outcome;
  SpeakerTagOutcome? get outcome => _outcome;

  Timer? _timer;
  int _generation = 0;
  bool _disposed = false;

  /// Starts following a tag that was just saved. A newer tag replaces the one on screen.
  void follow({required String personId, required String personName, required int linesLabeled}) {
    if (_disposed) return;
    final generation = ++_generation;
    _timer?.cancel();
    _outcome = SpeakerTagOutcome(personId: personId, personName: personName, linesLabeled: linesLabeled);
    notifyListeners();
    _schedule(generation, 0);
  }

  void dismiss() {
    _generation++;
    _timer?.cancel();
    _timer = null;
    if (_outcome == null) return;
    _outcome = null;
    notifyListeners();
  }

  /// Drops matches the user has answered in the review sheet.
  void removeMatch(api.PersonVoiceMatch match) {
    final current = _outcome;
    if (current == null) return;
    _outcome = current.copyWith(matches: [
      for (final m in current.matches)
        if (!identical(m, match)) m
    ]);
    notifyListeners();
  }

  void _schedule(int generation, int attempt) {
    _timer = Timer(pollInterval, () => unawaited(_poll(generation, attempt)));
  }

  Future<void> _poll(int generation, int attempt) async {
    final current = _outcome;
    if (current == null) return;
    final result = await _fetchPerson(current.personId);
    if (_disposed || generation != _generation) return;
    final state = switch (result) {
      ApiSuccess(:final data) => data.voiceLearningState,
      ApiFailure() => 'pending',
    };
    final lastAttempt = attempt + 1 >= maxPolls;
    if (state == 'pending' || state == 'unknown') {
      if (!lastAttempt) return _schedule(generation, attempt + 1);
      _settle(generation, 'needs_more_speech');
      return;
    }
    _settle(generation, state);
    if (state != 'learned') return;
    final matches = await _fetchMatches(current.personId);
    if (_disposed || generation != _generation) return;
    if (matches case ApiSuccess(:final data) when data.isNotEmpty) {
      _outcome = _outcome?.copyWith(matches: data);
      notifyListeners();
    }
  }

  void _settle(int generation, String state) {
    if (generation != _generation) return;
    _outcome = _outcome?.copyWith(voiceState: state);
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}

/// The card above the transcript after a person is tagged: what the tag did, whether the voice was
/// learned, and a way to label the same voice in earlier conversations.
class SpeakerTagOutcomeCard extends StatelessWidget {
  const SpeakerTagOutcomeCard({super.key, required this.outcome, required this.onClose, this.onReview});

  final SpeakerTagOutcome outcome;
  final VoidCallback onClose;

  /// Opens the earlier conversations where this voice was heard; null hides the action.
  final VoidCallback? onReview;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final state = outcome.voiceState;
    final learned = state == 'learned';
    return Semantics(
      container: true,
      liveRegion: true,
      child: Container(
        key: const Key('speaker_tag_outcome'),
        margin: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.xxs, OmiSpacing.sm),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    l10n.speakerTagPromptLabeledToast(outcome.personName),
                    style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                OmiIconButton(
                  key: const Key('speaker_tag_outcome_close'),
                  icon: const Icon(Icons.close, size: 16),
                  label: l10n.close,
                  color: OmiColors.textSecondary,
                  onPressed: onClose,
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(right: OmiSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _OutcomeRow(
                    leading: Icon(Icons.check, size: 18, color: OmiColors.success),
                    title: l10n.speakerLabelLinesLabeled(outcome.linesLabeled),
                  ),
                  const SizedBox(height: OmiSpacing.xs),
                  _OutcomeRow(
                    key: Key('speaker_tag_outcome_voice_$state'),
                    leading: state == 'pending'
                        ? const OmiSpinner(size: OmiSpinnerSize.small)
                        : Icon(
                            learned ? Icons.check : Icons.schedule,
                            size: 18,
                            color: learned ? OmiColors.success : OmiColors.warning,
                          ),
                    title: l10n.speakerLabelVoiceStatus(state),
                    detail: l10n.speakerLabelVoiceDetail(state, outcome.personName),
                  ),
                  if (outcome.matches.isNotEmpty && onReview != null) ...[
                    const SizedBox(height: OmiSpacing.xs),
                    _OutcomeRow(
                      leading: Icon(Icons.history, size: 18, color: OmiColors.textSecondary),
                      title: l10n.speakerLabelEarlierMatches(outcome.matches.length),
                      trailing: OmiButton.secondary(
                        key: const Key('speaker_tag_outcome_review'),
                        label: l10n.speakerLabelText('other', ''),
                        size: OmiButtonSize.compact,
                        onPressed: onReview,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OutcomeRow extends StatelessWidget {
  const _OutcomeRow({super.key, required this.leading, required this.title, this.detail, this.trailing});

  final Widget leading;
  final String title;
  final String? detail;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: detail == null ? CrossAxisAlignment.center : CrossAxisAlignment.start,
      children: [
        SizedBox(width: 20, height: 20, child: Center(child: ExcludeSemantics(child: leading))),
        const SizedBox(width: OmiSpacing.xs),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500)),
              if (detail != null)
                Text(detail!, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.35)),
            ],
          ),
        ),
        if (trailing != null) ...[const SizedBox(width: OmiSpacing.xs), trailing!],
      ],
    );
  }
}
