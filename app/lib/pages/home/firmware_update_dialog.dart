import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/firmware_update_prompt_coordinator.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/confirmation_dialog.dart';

class FirmwareUpdateStep {
  final String title;
  final String description;
  final FaIconData icon;
  final bool isLastStep;

  FirmwareUpdateStep({required this.title, required this.description, required this.icon, this.isLastStep = false});
}

/// The pre-flight sheet shown before every Omi firmware update: the server's checklist (minus the
/// battery item, which the page enforces in code) and the "do not close the app" warning, then one
/// Start Update button. Nothing is written to the device until it is pressed.
void showFirmwareUpdateSheet({
  required BuildContext context,
  required List<String> steps,
  required Future<void> Function() onUpdateStart,
}) {
  if (!nativePresentationEnabled) {
    showOmiSheet<void>(
      context: context,
      title: context.l10n.beforeUpdateMakeSure,
      builder: (context) => FirmwareUpdateSheet(steps: steps, onUpdateStart: onUpdateStart),
    );
    return;
  }
  unawaited(_showNativeFirmwareUpdateSheet(context, steps, onUpdateStart));
}

/// The same checklist as a native sheet. Start closes it and begins the update without waiting;
/// a host that cannot present it keeps the Flutter sheet.
Future<void> _showNativeFirmwareUpdateSheet(
    BuildContext context, List<String> steps, Future<void> Function() onUpdateStart) async {
  final l10n = context.l10n;
  const symbols = {'no_usb': 'powerplug', 'internet': 'wifi'};
  final checklist = {
    'no_usb': (l10n.firmwareDisconnectUsb, l10n.firmwareUsbWarning),
    'internet': (l10n.firmwareStableConnection, l10n.firmwareConnectWifi),
  };
  final keys = steps.where(checklist.containsKey).toSet();
  final result = await showIosNativeModal(
    context,
    title: l10n.beforeUpdateMakeSure,
    actions: [
      NativeRow('cancel', l10n.cancel),
      NativeRow('start', l10n.startUpdate),
    ],
    sections: [
      NativeSection('firmware_checklist', [
        for (final key in keys)
          NativeRow('firmware_step_$key', checklist[key]!.$1,
              kind: 'label', subtitle: checklist[key]!.$2, symbol: symbols[key]),
        NativeRow('firmware_warning', l10n.firmwareUpdateWarning, kind: 'label', symbol: 'exclamationmark.triangle'),
      ]),
    ],
  );
  if (result == null) {
    if (!context.mounted) return;
    showOmiSheet<void>(
      context: context,
      title: l10n.beforeUpdateMakeSure,
      builder: (context) => FirmwareUpdateSheet(steps: steps, onUpdateStart: onUpdateStart),
    );
    return;
  }
  if (result.action == 'start') unawaited(onUpdateStart());
}

/// The page an accepted update prompt opens: the Wi-Fi OTA page for OmiGlass, otherwise the DFU page.
Widget firmwareUpdatePageFor({required bool omiGlass, BtDevice? device, Map<String, dynamic>? omiGlassDetails}) =>
    omiGlass
        ? OmiGlassOtaUpdate(device: device, latestFirmwareDetails: omiGlassDetails)
        : FirmwareUpdate(device: device);

/// Asks whether to install [version] now. [coordinator] owns the prompt: its withdrawal closes the
/// prompt without deferring or opening anything, Later defers this version, and Update runs [onAccept]
/// with the navigator to push the update page on. The prompt is completed however it ends.
Future<void> presentFirmwareUpdatePrompt(
  BuildContext context, {
  required FirmwareUpdatePromptCoordinator coordinator,
  required FirmwareUpdatePrompt prompt,
  required String version,
  required void Function(NavigatorState navigator) onAccept,
}) async {
  if (!nativePresentationEnabled) {
    return _presentClassicFirmwareUpdatePrompt(context, coordinator, prompt, version, onAccept);
  }
  final navigator = Navigator.of(context);
  final withdrawn = Completer<void>();
  final l10n = context.l10n;
  try {
    coordinator.attachDismissal(prompt, () {
      if (!withdrawn.isCompleted) withdrawn.complete();
    });
    final result = await showIosNativeModal(
      context,
      title: l10n.firmwareUpdateAvailable,
      alert: true,
      dismissible: false,
      cancelId: 'later',
      dismissSignal: withdrawn.future,
      actions: [
        NativeRow('later', l10n.later),
        NativeRow('update', l10n.update),
      ],
      sections: [
        NativeSection('firmware_prompt', [
          NativeRow('firmware_prompt_message', l10n.firmwareUpdateAvailableDescription(version), kind: 'label'),
        ]),
      ],
    );
    if (result == null) {
      // The Flutter dialog attaches its own dismissal, so a withdrawal that already happened closes it.
      if (context.mounted) await _presentClassicFirmwareUpdatePrompt(context, coordinator, prompt, version, onAccept);
      return;
    }
    if (result.action == 'update') {
      if (!coordinator.accept(prompt)) return;
      Logger.info('Firmware update prompt accepted');
      if (navigator.mounted) onAccept(navigator);
    } else if (result.reason == 'cancel') {
      if (coordinator.defer(prompt)) Logger.info('Firmware update prompt deferred by user');
    }
  } finally {
    coordinator.complete(prompt);
  }
}

Future<void> _presentClassicFirmwareUpdatePrompt(BuildContext context, FirmwareUpdatePromptCoordinator coordinator,
    FirmwareUpdatePrompt prompt, String version, void Function(NavigatorState navigator) onAccept) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) {
      final route = ModalRoute.of(dialogContext);
      final navigator = Navigator.of(dialogContext);
      coordinator.attachDismissal(prompt, () {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!dialogContext.mounted || route == null || !route.isActive) return;
          if (route.isCurrent) {
            navigator.pop();
          } else {
            navigator.removeRoute(route);
          }
        });
      });

      return ConfirmationDialog(
        title: dialogContext.l10n.firmwareUpdateAvailable,
        description: dialogContext.l10n.firmwareUpdateAvailableDescription(version),
        confirmText: dialogContext.l10n.update,
        cancelText: dialogContext.l10n.later,
        onConfirm: () {
          if (!coordinator.accept(prompt)) return;
          Logger.info('Firmware update prompt accepted');
          onAccept(navigator);
        },
        onCancel: () {
          if (coordinator.defer(prompt)) {
            Logger.info('Firmware update prompt deferred by user');
          }
        },
      );
    },
  ).whenComplete(() {
    coordinator.complete(prompt);
  });
}

class FirmwareUpdateSheet extends StatefulWidget {
  final Future<void> Function() onUpdateStart;
  final List<String> steps;

  const FirmwareUpdateSheet({super.key, required this.onUpdateStart, required this.steps});

  @override
  State<FirmwareUpdateSheet> createState() => _FirmwareUpdateSheetState();
}

class _FirmwareUpdateSheetState extends State<FirmwareUpdateSheet> {
  late final List<String> stepKeys;
  bool hasUsbStep = false;

  @override
  void initState() {
    super.initState();
    // Battery is checked by the app before this sheet opens; a checklist line would only ask the
    // reader to vouch for something the app already knows.
    stepKeys = widget.steps.where((key) => key != 'battery').toList();
    hasUsbStep = widget.steps.contains('no_usb');
  }

  Map<String, FirmwareUpdateStep> _getStepMap(BuildContext context) {
    return {
      'no_usb': FirmwareUpdateStep(
        title: context.l10n.firmwareDisconnectUsb,
        description: context.l10n.firmwareUsbWarning,
        icon: FontAwesomeIcons.plug,
      ),
      'battery': FirmwareUpdateStep(
        title: context.l10n.firmwareBatteryAbove15,
        description: context.l10n.firmwareEnsureBattery,
        icon: FontAwesomeIcons.batteryHalf,
      ),
      'internet': FirmwareUpdateStep(
        title: context.l10n.firmwareStableConnection,
        description: context.l10n.firmwareConnectWifi,
        icon: FontAwesomeIcons.wifi,
      ),
    };
  }

  /// Closes the sheet and starts. A failure is shown by the update page's failed state (cause,
  /// Try Again, Contact Support), not a toast from a sheet that is already gone.
  void _onConfirmed() {
    Navigator.of(context).pop();
    unawaited(widget.onUpdateStart());
  }

  @override
  Widget build(BuildContext context) {
    final stepMap = _getStepMap(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final key in stepKeys)
            if (stepMap[key] != null) _buildStepItem(stepMap[key]!),
          Container(
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(
              color: OmiColors.warning.withValues(alpha: 0.12),
              borderRadius: OmiRadius.mdAll,
            ),
            child: Row(
              children: [
                ExcludeSemantics(
                  child: FaIcon(FontAwesomeIcons.triangleExclamation, color: OmiColors.warning, size: 18),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(child: Text(context.l10n.firmwareUpdateWarning, style: OmiType.subhead.copyWith(height: 1.4))),
              ],
            ),
          ),
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
            key: const Key('firmware_update_sheet_start'),
            label: context.l10n.startUpdate,
            expand: true,
            onPressed: _onConfirmed,
          ),
        ],
      ),
    );
  }

  Widget _buildStepItem(FirmwareUpdateStep step) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
      child: Container(
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
              child: Center(child: FaIcon(step.icon, size: 18, color: OmiColors.textPrimary)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(step.title, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(height: OmiSpacing.xxs),
                  Text(step.description, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.3)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
