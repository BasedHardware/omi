import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/home/widgets/payment_issue_row.dart';
import 'package:omi/pages/review/widgets/review_entry_card.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/providers/usage_provider.dart';

/// What can ask for the reader's attention above Home's list, most important first.
enum HomePrompt { payment, firmware, voiceProfile, review }

/// The one prompt Home shows, or null. Pure, so the order is tested without widgets.
HomePrompt? homePrompt({
  required bool paymentIssue,
  required bool firmwareUpdate,
  required bool voiceProfileMissing,
  required bool reviewWaiting,
}) {
  if (paymentIssue) return HomePrompt.payment;
  if (firmwareUpdate) return HomePrompt.firmware;
  if (voiceProfileMissing) return HomePrompt.voiceProfile;
  if (reviewWaiting) return HomePrompt.review;
  return null;
}

/// One slot above Home's list holding at most one prompt, chosen by [homePrompt]. The others wait
/// their turn instead of stacking. Review questions are still fetched while another prompt shows,
/// so they appear as soon as the slot frees up.
class HomePromptSlot extends StatefulWidget {
  const HomePromptSlot({super.key});

  @override
  State<HomePromptSlot> createState() => _HomePromptSlotState();
}

class _HomePromptSlotState extends State<HomePromptSlot> with WidgetsBindingObserver {
  /// The Review prompt hides when nothing is waiting, so it cannot be the only way new questions
  /// arrive: coming back to the app looks again, at most this often.
  static const _resumeRefreshInterval = Duration(minutes: 5);
  DateTime _lastLoad = DateTime.now();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final review = context.read<ReviewProvider?>();
      review?.reportReleaseChannel();
      if (review != null && review.availability == ReviewAvailability.unknown) review.load();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !mounted) return;
    if (DateTime.now().difference(_lastLoad) < _resumeRefreshInterval) return;
    final review = context.read<ReviewProvider?>();
    if (review == null || review.availability == ReviewAvailability.off) return;
    _lastLoad = DateTime.now();
    review.load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final payment = context
        .select<UsageProvider?, bool>((u) => u?.showSubscriptionUI == true && u?.subscription?.paymentIssue != null);
    final (firmware, deviceReady) = context.select<DeviceProvider?, (bool, bool)>((d) => (
          d?.havingNewFirmware == true,
          d != null && d.pairedDevice != null && d.isConnected && d.pairedDevice?.firmwareRevision != '1.0.2',
        ));
    final voiceMissing =
        deviceReady && context.select<HomeProvider?, bool>((h) => h != null && !h.isLoading && !h.hasSpeakerProfile);
    final review = context.select<ReviewProvider?, bool>((r) => r != null && r.isOn && r.items.isNotEmpty);
    final prompt = homePrompt(
      paymentIssue: payment,
      firmwareUpdate: firmware,
      voiceProfileMissing: voiceMissing,
      reviewWaiting: review,
    );
    return switch (prompt) {
      HomePrompt.payment => const PaymentIssueRow(),
      HomePrompt.firmware => const UpdateFirmwareCardWidget(),
      HomePrompt.voiceProfile => const SpeechProfileCardWidget(),
      HomePrompt.review => const ReviewEntryCard(),
      null => const SizedBox.shrink(),
    };
  }
}
