import 'package:flutter/material.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/on_device/on_device_settings_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Settings › Transcription's "This phone" pieces: what is still missing before the phone can
/// transcribe, and the free plan's cloud minutes. Stateless; the page owns the choice and its effects.

/// "258 of 300 min left · resets Dec 1" for a plan with a monthly cloud allowance, else null.
String? cloudUsageLine(BuildContext context, UserSubscriptionResponse? subscription,
    {required bool showSubscriptionUI}) {
  if (!showSubscriptionUI || subscription == null || subscription.subscription.plan.hasUnlimitedTranscription) {
    return null;
  }
  final limit = subscription.transcriptionSecondsLimit;
  if (limit <= 0) return null;
  final left = ((limit - subscription.transcriptionSecondsUsed).clamp(0, limit) / 60).floor();
  return context.l10n.cloudMinutesLeft(
    left,
    (limit / 60).round(),
    OmiDateFormat.of(context).date(onDeviceUsageResetsOn(DateTime.now())),
  );
}

/// Cloud minutes a pinned phone choice could use again after the monthly reset, or null.
int? switchBackMinutes(UserSubscriptionResponse? subscription, {required bool pinnedOnPhone}) {
  final allowance = subscription?.transcriptionAllowance;
  final remaining = allowance?.remainingSeconds;
  if (!pinnedOnPhone || allowance == null || !allowance.isManaged || remaining == null || remaining < 60) return null;
  return (remaining / 60).floor();
}

/// "N cloud minutes available · Switch back": no pop-up, only here (David, 2026-11-16).
class TranscriptionSwitchBackGroup extends StatelessWidget {
  const TranscriptionSwitchBackGroup({super.key, required this.minutes, required this.onSwitchBack});

  final int minutes;
  final VoidCallback onSwitchBack;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiSettingsGroup(
      children: [
        OmiSettingsRow(
          key: const Key('transcription_switch_back'),
          title: l10n.cloudMinutesAvailable(minutes),
          trailing: OmiButton(label: l10n.switchBack, size: OmiButtonSize.compact, onPressed: onSwitchBack),
        ),
      ],
    );
  }
}

/// iOS speech-recognition permission, asked only where the reader chose the phone.
class PhoneSpeechPermissionGroup extends StatelessWidget {
  const PhoneSpeechPermissionGroup({super.key, required this.canAsk, required this.onPressed});

  /// True when iOS can still show its prompt; false sends the reader to the app's Settings.
  final bool canAsk;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiSettingsGroup(
      header: l10n.setUpThisPhone,
      children: [
        OmiSettingsRow(
          key: const Key('transcription_phone_permission'),
          title: l10n.speechRecognition,
          subtitle: l10n.audioStaysOnPhone,
          trailing: OmiButton(
            label: canAsk ? l10n.allow : l10n.openSettings,
            size: OmiButtonSize.compact,
            onPressed: onPressed,
          ),
        ),
      ],
    );
  }
}

/// Android speech model: its size with Download now or On Wi-Fi later. Wi-Fi is never required.
class PhoneModelSetupGroup extends StatelessWidget {
  const PhoneModelSetupGroup({
    super.key,
    required this.megabytes,
    required this.waitingForWifi,
    required this.onDownloadNow,
    required this.onWifiLater,
  });

  final int megabytes;
  final bool waitingForWifi;
  final VoidCallback onDownloadNow;

  /// Null hides "On Wi-Fi later" (the background download serves only the default model).
  final VoidCallback? onWifiLater;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (waitingForWifi) {
      return OmiSettingsGroup(
        header: l10n.setUpThisPhone,
        children: [
          OmiSettingsRow(
            title: l10n.onDeviceSpeechModel,
            value: l10n.onDeviceWaitingForWifi,
            trailing:
                OmiButton.tertiary(label: l10n.downloadNow, size: OmiButtonSize.compact, onPressed: onDownloadNow),
          ),
        ],
      );
    }
    return OmiSettingsGroup(
      header: l10n.setUpThisPhone,
      children: [
        OmiSettingsRow(
          key: const Key('transcription_phone_model'),
          title: l10n.onDeviceSpeechModel,
          subtitle: l10n.onDeviceModelDownloadSize(megabytes),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: OmiButton(
                    key: const Key('transcription_phone_download_now'),
                    label: l10n.downloadNow,
                    onPressed: onDownloadNow),
              ),
              if (onWifiLater case final later?) ...[
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: OmiButton.secondary(
                      key: const Key('transcription_phone_download_wifi'), label: l10n.onWifiLater, onPressed: later),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
