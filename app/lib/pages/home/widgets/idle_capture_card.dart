import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/devices/add_device_page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Today while nothing is listening (Rev 3, device-agnostic): the live card's quiet twin. The orb
/// sits grey; Start listening records with this phone (a listening wearable asks first, as the
/// record button did); the second capsule adds a device, or opens Devices when one is paired.
///
/// It takes the live card's place: hidden whenever the live card (or a call) is showing.
class IdleCaptureCard extends StatelessWidget {
  const IdleCaptureCard({super.key});

  /// Whether [ConversationCaptureWidget] shows something now (the same test it uses).
  static bool isCapturing(CaptureProvider capture) {
    final batch =
        capture.isPhoneMicBatchRecording || (SharedPreferencesUtil().batchModeEnabled && capture.havingRecordingDevice);
    final phoneLive = capture.recordingState == RecordingState.record ||
        capture.recordingState == RecordingState.initialising ||
        capture.recordingState == RecordingState.interrupted ||
        capture.recordingState == RecordingState.systemAudioRecord ||
        capture.isPhoneMicPaused;
    return capture.liveCaptureSource != null || phoneLive || batch;
  }

  @override
  Widget build(BuildContext context) {
    final callState = context.select<PhoneCallProvider, PhoneCallState>((p) => p.callState);
    final onCall = callState == PhoneCallState.active ||
        callState == PhoneCallState.connecting ||
        callState == PhoneCallState.ringing;
    final capturing = context.select<CaptureProvider, bool>(isCapturing);
    if (onCall || capturing) return const SizedBox.shrink();
    final paired = context.select<DeviceProvider, bool>((d) => (d.pairedDevice?.id ?? '').isNotEmpty);
    final l10n = context.l10n;
    return Padding(
      key: const ValueKey('idle_capture_card'),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.sm),
      child: OmiCard(
        radius: OmiRadius.cardLarge,
        padding: const EdgeInsets.all(OmiSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const OmiOrb(size: 44, live: false),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l10n.notListeningTitle, style: OmiType.headline),
                      const SizedBox(height: 2),
                      Text(
                        l10n.notListeningSubtitle,
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.md),
            Row(
              children: [
                Expanded(
                  child: LiveCaptureAction(
                    key: const ValueKey('idle_capture_start'),
                    label: l10n.startListening,
                    icon: Icons.mic_rounded,
                    primary: true,
                    onPressed: () => PhoneCapture.start(context),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: LiveCaptureAction(
                    key: const ValueKey('idle_capture_devices'),
                    label: paired ? l10n.manageDevices : l10n.addADevice,
                    icon: paired ? Icons.tune_rounded : Icons.add_rounded,
                    primary: false,
                    onPressed: () {
                      OmiHaptics.selection();
                      if (paired) {
                        context.read<HomeProvider>().setIndex(3);
                      } else {
                        routeToPage(context, const AddDevicePage());
                      }
                    },
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
