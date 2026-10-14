import 'package:flutter/material.dart';

import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum OnDeviceAtCapChoice { transcribeOnPhone, upgrade }

/// Offered once when the month's live hours run out: keep going on the phone (included) or
/// upgrade. Returns the reader's choice, or null when they close the sheet. Recording continues
/// either way.
Future<OnDeviceAtCapChoice?> showOnDeviceAtCapSheet(BuildContext context, {DateTime? liveHoursReturnOn}) {
  return showOmiSheet<OnDeviceAtCapChoice>(
    context: context,
    builder: (sheetContext) => OnDeviceAtCapSheet(
      liveHoursReturnOn: liveHoursReturnOn,
      onContinue: (choice) => Navigator.of(sheetContext).pop(choice),
    ),
  );
}

class OnDeviceAtCapSheet extends StatefulWidget {
  const OnDeviceAtCapSheet({super.key, required this.onContinue, this.liveHoursReturnOn});

  final ValueChanged<OnDeviceAtCapChoice> onContinue;

  /// When live hours reset; the sentence is left out when unknown.
  final DateTime? liveHoursReturnOn;

  @override
  State<OnDeviceAtCapSheet> createState() => _OnDeviceAtCapSheetState();
}

class _OnDeviceAtCapSheetState extends State<OnDeviceAtCapSheet> {
  OnDeviceAtCapChoice _choice = OnDeviceAtCapChoice.transcribeOnPhone;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final returnOn = widget.liveHoursReturnOn;
    final body = returnOn == null
        ? l10n.onDeviceAtCapBody
        : '${l10n.onDeviceAtCapBody} ${l10n.onDeviceLiveHoursReturn(OmiDateFormat.of(context).date(returnOn))}';
    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(header: true, child: Text(l10n.onDeviceAtCapTitle, style: OmiType.title2)),
          const SizedBox(height: OmiSpacing.xs),
          Text(body, style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4)),
          const SizedBox(height: OmiSpacing.lg),
          OnDeviceChoiceCard(
            key: const Key('on_device_at_cap_phone'),
            title: l10n.onDeviceTranscribeOnPhone,
            badge: l10n.onDeviceIncluded,
            body: l10n.onDeviceOptionChargingBody,
            selected: _choice == OnDeviceAtCapChoice.transcribeOnPhone,
            onSelected: () => setState(() => _choice = OnDeviceAtCapChoice.transcribeOnPhone),
          ),
          const SizedBox(height: OmiSpacing.sm),
          OnDeviceChoiceCard(
            key: const Key('on_device_at_cap_upgrade'),
            title: l10n.upgradeToPro,
            body: l10n.onDeviceUpgradeBody,
            selected: _choice == OnDeviceAtCapChoice.upgrade,
            onSelected: () => setState(() => _choice = OnDeviceAtCapChoice.upgrade),
          ),
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
            key: const Key('on_device_at_cap_continue'),
            label: l10n.continueButton,
            expand: true,
            onPressed: () => widget.onContinue(_choice),
          ),
          const SizedBox(height: OmiSpacing.sm),
          Text(
            l10n.onDeviceAtCapFooter,
            textAlign: TextAlign.center,
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, height: 1.35),
          ),
        ],
      ),
    );
  }
}
