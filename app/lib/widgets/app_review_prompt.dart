import 'dart:async';

import 'package:flutter/material.dart';
import 'package:in_app_review/in_app_review.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/services/app_review_tuning.dart';
import 'package:omi/services/experiments/onboarding_setup_rating_prompt.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/review_reading_moment.dart';

/// The shared admission boundary for both reading surfaces. Passive wearable
/// capture can continue; phone recording and calls must remain uninterrupted.
class AppReviewPrompt extends StatefulWidget {
  const AppReviewPrompt({
    super.key,
    required this.contentId,
    required this.moment,
    required this.enabled,
    required this.child,
    this.service,
    this.firstSummaryAskDelay = defaultFirstSummaryAskDelay,
    this.isRatingAskEnabled,
    this.requestStoreReview,
  });

  /// How long the first summary after onboarding stays open before it asks "Are you enjoying Omi?".
  static const defaultFirstSummaryAskDelay = Duration(seconds: 7);

  @visibleForTesting
  static void resetSessionForTesting() => _AppReviewPromptState._ratingAskedThisSession = false;

  final String contentId;
  final AppReviewMoment moment;
  final bool enabled;
  final Widget child;
  final AppReviewService? service;
  final Duration firstSummaryAskDelay;

  /// Kill switch for the "Are you enjoying Omi?" ask; defaults to the onboarding rating flag.
  final Future<bool> Function()? isRatingAskEnabled;

  /// Opens the store review sheet after "Yes"; defaults to `in_app_review`. Injectable for tests.
  final Future<void> Function()? requestStoreReview;

  @override
  State<AppReviewPrompt> createState() => _AppReviewPromptState();
}

class _AppReviewPromptState extends State<AppReviewPrompt> {
  /// The "Are you enjoying Omi?" ask fires at most once per app session; the native reading
  /// prompt stays quiet for that session so the user is never asked twice in a row.
  static bool _ratingAskedThisSession = false;

  Duration _readingDuration = const Duration(seconds: AppReviewTuning.defaultReadingSeconds);
  bool _tuningReady = false;
  Timer? _firstSummaryTimer;

  @override
  void initState() {
    super.initState();
    AppReviewTuning.readingDuration().then((duration) {
      if (mounted) {
        setState(() {
          _readingDuration = duration;
          _tuningReady = true;
        });
      }
    }, onError: (_) {
      if (mounted) {
        setState(() => _tuningReady = true);
      }
    });
  }

  bool _available(BuildContext context) {
    final preferences = SharedPreferencesUtil();
    final capture = context.read<CaptureProvider?>();
    return preferences.onboardingCompleted &&
        preferences.uid.isNotEmpty &&
        capture?.isCallActive != true &&
        capture?.isPhoneMicBatchRecording != true &&
        !const {
          RecordingState.initialising,
          RecordingState.record,
          RecordingState.systemAudioRecord,
          RecordingState.interrupted,
          RecordingState.pause,
        }.contains(capture?.recordingState) &&
        !const {
          PhoneCallState.connecting,
          PhoneCallState.ringing,
          PhoneCallState.active,
        }.contains(PhoneCallProvider.callStateListenable.value);
  }

  @override
  void dispose() {
    _firstSummaryTimer?.cancel();
    super.dispose();
  }

  bool get _firstSummaryAskPending =>
      widget.moment == AppReviewMoment.conversationRead &&
      !_ratingAskedThisSession &&
      SharedPreferencesUtil().firstSummaryRatingPending;

  bool _canAskNow(BuildContext context) =>
      mounted &&
      widget.enabled &&
      widget.contentId.isNotEmpty &&
      (ModalRoute.of(context)?.isCurrent ?? true) &&
      (WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.resumed) == AppLifecycleState.resumed &&
      _available(context);

  /// Arms the first-summary ask while this summary is open and appropriate; disarms otherwise.
  void _syncFirstSummaryAsk() {
    if (!mounted) return;
    if (_firstSummaryAskPending && _canAskNow(context)) {
      _firstSummaryTimer ??= Timer(widget.firstSummaryAskDelay, _askFirstSummaryRating);
    } else {
      _firstSummaryTimer?.cancel();
      _firstSummaryTimer = null;
    }
  }

  Future<void> _askFirstSummaryRating() async {
    _firstSummaryTimer = null;
    if (!_firstSummaryAskPending || !_canAskNow(context)) return;
    bool enabled;
    try {
      enabled = await (widget.isRatingAskEnabled ?? OnboardingSetupRatingPromptGate.isEnabled)();
    } catch (_) {
      enabled = false;
    }
    // Flag off: keep it pending so a later summary can ask once the flag is on.
    if (!mounted || !enabled || !_firstSummaryAskPending || !_canAskNow(context)) return;
    _ratingAskedThisSession = true;
    SharedPreferencesUtil().firstSummaryRatingPending = false;
    const TypedEvents().emit(const FirstSummaryRatingPromptShown());
    final l10n = context.l10n;
    final enjoying = await showOmiConfirm(
      context,
      title: l10n.onboardingRatingPromptTitle,
      confirmLabel: l10n.onboardingRatingPromptYes,
      cancelLabel: l10n.onboardingRatingPromptNo,
      barrierDismissible: false,
    );
    const TypedEvents().emit(FirstSummaryRatingPromptAnswered(
      answer: enjoying ? FirstSummaryRatingPromptAnsweredAnswer.yes : FirstSummaryRatingPromptAnsweredAnswer.no,
    ));
    if (!enjoying) return;
    OmiHaptics.success();
    try {
      // The store decides whether its sheet appears (and never on the simulator).
      await (widget.requestStoreReview ?? InAppReview.instance.requestReview)();
    } catch (error) {
      debugPrint('AppReviewPrompt: review request failed: $error');
    }
  }

  @override
  Widget build(BuildContext context) {
    // Rebuild when a call/recording begins, including while the delay is armed.
    context.watch<CaptureProvider?>();
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFirstSummaryAsk());
    final owner = SharedPreferencesUtil().uid;
    final reviewService = widget.service ?? AppReviewService();
    return ValueListenableBuilder<PhoneCallState>(
      valueListenable: PhoneCallProvider.callStateListenable,
      builder: (context, _, child) => ReviewReadingMoment(
        contentId: '$owner:${widget.contentId}',
        enabled: _tuningReady &&
            !_ratingAskedThisSession &&
            !_firstSummaryAskPending &&
            widget.enabled &&
            widget.contentId.isNotEmpty &&
            _available(context),
        minimumReadingDuration: _readingDuration,
        onFinishedReading: (isStillAppropriate) => reviewService.requestReview(
          moment: widget.moment,
          isStillAppropriate: () =>
              context.mounted && isStillAppropriate() && SharedPreferencesUtil().uid == owner && _available(context),
        ),
        child: child!,
      ),
      child: widget.child,
    );
  }
}
