import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
  showOmiSheet<void>(
    context: context,
    title: context.l10n.beforeUpdateMakeSure,
    builder: (context) => FirmwareUpdateSheet(steps: steps, onUpdateStart: onUpdateStart),
  );
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
                const ExcludeSemantics(
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
        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
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
