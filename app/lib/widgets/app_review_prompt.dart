import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/services/app_review_tuning.dart';
import 'package:omi/utils/enums.dart';
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
  });

  final String contentId;
  final AppReviewMoment moment;
  final bool enabled;
  final Widget child;
  final AppReviewService? service;

  @override
  State<AppReviewPrompt> createState() => _AppReviewPromptState();
}

class _AppReviewPromptState extends State<AppReviewPrompt> {
  Duration _readingDuration = const Duration(seconds: AppReviewTuning.defaultReadingSeconds);
  bool _tuningReady = false;

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
  Widget build(BuildContext context) {
    // Rebuild when a call/recording begins, including while the delay is armed.
    context.watch<CaptureProvider?>();
    final owner = SharedPreferencesUtil().uid;
    final reviewService = widget.service ?? AppReviewService();
    return ValueListenableBuilder<PhoneCallState>(
      valueListenable: PhoneCallProvider.callStateListenable,
      builder: (context, _, child) => ReviewReadingMoment(
        contentId: '$owner:${widget.contentId}',
        enabled: _tuningReady && widget.enabled && widget.contentId.isNotEmpty && _available(context),
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
