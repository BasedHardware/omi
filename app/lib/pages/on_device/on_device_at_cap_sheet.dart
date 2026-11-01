import 'package:flutter/material.dart';
import 'package:omi/backend/schema/gen/storefront_wire.g.dart';

import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum OnDeviceAtCapChoice { transcribeOnPhone, upgrade }

/// Offered once when this month's usage limit is reached: keep going on the phone (included) or
/// upgrade. Returns the reader's choice, or null when they close the sheet. Recording continues
/// either way.
Future<OnDeviceAtCapChoice?> showOnDeviceAtCapSheet(BuildContext context,
    {DateTime? liveHoursReturnOn, GeneratedStorefrontCapChoice? copy, ValueChanged<bool>? onDontAskAgain}) {
  return showOmiSheet<OnDeviceAtCapChoice>(
    context: context,
    builder: (sheetContext) => OnDeviceAtCapSheet(
      liveHoursReturnOn: liveHoursReturnOn,
      copy: copy,
      onDontAskAgain: onDontAskAgain,
      onContinue: (choice) => Navigator.of(sheetContext).pop(choice),
    ),
  );
}

class OnDeviceAtCapSheet extends StatefulWidget {
  const OnDeviceAtCapSheet(
      {super.key, required this.onContinue, this.liveHoursReturnOn, this.copy, this.onDontAskAgain});

  final ValueChanged<OnDeviceAtCapChoice> onContinue;
  final GeneratedStorefrontCapChoice? copy;
  final ValueChanged<bool>? onDontAskAgain;

  /// When usage resets; the sentence is left out when unknown.
  final DateTime? liveHoursReturnOn;

  @override
  State<OnDeviceAtCapSheet> createState() => _OnDeviceAtCapSheetState();
}

class _OnDeviceAtCapSheetState extends State<OnDeviceAtCapSheet> {
  bool _dontAskAgain = false;
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
          Semantics(
            header: true,
            child: Text(
              widget.copy?.title ?? l10n.onDeviceAtCapTitle,
              style: OmiType.title2,
            ),
          ),
          const SizedBox(height: OmiSpacing.xs),
          Text(widget.copy?.body ?? body, style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4)),
          const SizedBox(height: OmiSpacing.lg),
          OnDeviceChoiceCard(
            key: const Key('on_device_at_cap_phone'),
            title: widget.copy?.onDeviceLabel ?? l10n.onDeviceTranscribeOnPhone,
            badge: l10n.onDeviceIncluded,
            body: l10n.onDeviceOptionChargingBody,
            selected: _choice == OnDeviceAtCapChoice.transcribeOnPhone,
            onSelected: () => setState(() => _choice = OnDeviceAtCapChoice.transcribeOnPhone),
          ),
          const SizedBox(height: OmiSpacing.sm),
          OnDeviceChoiceCard(
            key: const Key('on_device_at_cap_upgrade'),
            title: widget.copy?.upgradeLabel ?? l10n.upgradeToPro,
            body: widget.copy?.onDeviceUpgradeLine ?? l10n.onDeviceUpgradeBody,
            selected: _choice == OnDeviceAtCapChoice.upgrade,
            onSelected: () => setState(() => _choice = OnDeviceAtCapChoice.upgrade),
          ),
          const SizedBox(height: OmiSpacing.lg),
          if (widget.copy != null)
            CheckboxListTile(
              title: Text(widget.copy!.dontAskAgainLabel,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
              value: _dontAskAgain,
              onChanged: (value) {
                setState(() => _dontAskAgain = value == true);
                widget.onDontAskAgain?.call(_dontAskAgain);
              },
            ),
          OmiButton(
            key: const Key('on_device_at_cap_continue'),
            label: widget.copy == null
                ? l10n.continueButton
                : _choice == OnDeviceAtCapChoice.upgrade
                    ? widget.copy!.upgradeLabel
                    : widget.copy!.onDeviceLabel,
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
