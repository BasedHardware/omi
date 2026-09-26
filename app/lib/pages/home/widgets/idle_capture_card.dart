import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/devices/add_device_page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';

/// Today while nothing is listening (Rev 3, device-agnostic): the live card's quiet twin. The orb
/// sits grey and Start is the one primary action: a connected wearable the reader stopped listens
/// again; otherwise this phone records (a listening wearable asks first, as the record button did).
/// The second capsule adds a device, or opens Devices when one is paired.
///
/// It takes the live card's place: hidden whenever the live card (or a call) is showing.
class IdleCaptureCard extends StatelessWidget {
  const IdleCaptureCard({super.key});

  /// Whether [ConversationCaptureWidget] shows something now (the same test it uses).
  static bool isCapturing(CaptureProvider capture) {
    // Stopped is not capturing: the pendant waits here for Start. So is a Stop on its way.
    if (capture.isStopping || (capture.isCaptureStopped && !_phoneLive(capture))) return false;
    final batch =
        capture.isPhoneMicBatchRecording || (SharedPreferencesUtil().batchModeEnabled && capture.havingRecordingDevice);
    return capture.liveCaptureSource != null || _phoneLive(capture) || batch;
  }

  static bool _phoneLive(CaptureProvider capture) =>
      capture.recordingState == RecordingState.record ||
      capture.recordingState == RecordingState.initialising ||
      capture.recordingState == RecordingState.interrupted ||
      capture.recordingState == RecordingState.systemAudioRecord ||
      capture.isPhoneMicPaused;

  /// Start for a wearable the reader stopped: it listens again, as a new conversation. Says so when
  /// it does not, rather than leaving the button looking dead.
  static Future<void> _startWearable(BuildContext context) async {
    final capture = context.read<CaptureProvider>();
    OmiHaptics.medium();
    try {
      await capture.startCapture();
    } catch (_) {
      if (context.mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
      return;
    }
    if (capture.isCaptureStopped && context.mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
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
    // A connected wearable the reader stopped (or is stopping): Start wakes it rather than the phone.
    final stoppedSource = context.select<CaptureProvider, String?>(
      (c) => (c.isCaptureStopped || (c.isStopping && (c.liveCaptureSource ?? 'phone') != 'phone')) &&
              c.havingRecordingDevice
          ? (c.liveCaptureSource ?? 'omi')
          : null,
    );
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
                        stoppedSource == null
                            ? l10n.notListeningSubtitle
                            : '${CaptureSources.label(context, stoppedSource)} · ${l10n.deviceReady}',
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
                    label: l10n.start,
                    icon: Icons.fiber_manual_record_rounded,
                    primary: true,
                    onPressed: () => stoppedSource != null ? _startWearable(context) : PhoneCapture.start(context),
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
                        // Devices live in Settings now that Apps has the tab.
                        openSettingsDestination(context, SettingsDestination.deviceGroup);
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
