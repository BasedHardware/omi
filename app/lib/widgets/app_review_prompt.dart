import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/widgets/review_reading_moment.dart';

/// The shared admission boundary for both reading surfaces. Passive wearable
/// capture can continue; phone recording and calls must remain uninterrupted.
class AppReviewPrompt extends StatelessWidget {
  const AppReviewPrompt({
    super.key,
    required this.contentId,
    required this.moment,
    required this.enabled,
    required this.child,
    this.service,
  });

  final String contentId;
  final AppReviewMoment moment;
  final bool enabled;
  final Widget child;
  final AppReviewService? service;

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
        !const {PhoneCallState.connecting, PhoneCallState.ringing, PhoneCallState.active}
            .contains(PhoneCallProvider.callStateListenable.value);
  }

  @override
  Widget build(BuildContext context) {
    // Rebuild when a call/recording begins, including while the delay is armed.
    context.watch<CaptureProvider?>();
    final owner = SharedPreferencesUtil().uid;
    final reviewService = service ?? AppReviewService();
    return ValueListenableBuilder<PhoneCallState>(
      valueListenable: PhoneCallProvider.callStateListenable,
      builder: (context, _, child) => ReviewReadingMoment(
        contentId: '$owner:$contentId',
        enabled: enabled && contentId.isNotEmpty && _available(context),
        onEngaged: () => unawaited(reviewService.recordEngagement()),
        onFinishedReading: (isStillAppropriate) => reviewService.requestReview(
          moment: moment,
          isStillAppropriate: () =>
              context.mounted && isStillAppropriate() && SharedPreferencesUtil().uid == owner && _available(context),
        ),
        child: child!,
      ),
      child: child,
    );
  }
}
