import 'package:flutter/material.dart';

import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

// The free plan's monthly-cap sheet. It owns only the layout and the reader's choice; what each
// choice opens, and how often the sheet may show, belong to FreemiumSwitchHandler.

enum FreeCapChoice { upgrade, transcribeOnPhone }

/// The free plan's one prompt at the monthly cloud cap (David, 2026-11-16): Omi Pro first and
/// primary, transcribing on this phone second. Returns the reader's choice, or null when they close
/// the sheet. Capture is never interrupted; the sheet waits for it to stop.
Future<FreeCapChoice?> showFreeCapSheet(BuildContext context, {required int capMinutes}) {
  return showOmiSheet<FreeCapChoice>(
    context: context,
    builder: (sheetContext) => FreeCapSheet(
      capMinutes: capMinutes,
      onChoice: (choice) => Navigator.of(sheetContext).pop(choice),
    ),
  );
}

class FreeCapSheet extends StatelessWidget {
  const FreeCapSheet({super.key, required this.capMinutes, required this.onChoice});

  /// The plan's monthly cloud minutes, as the title states them.
  final int capMinutes;
  final ValueChanged<FreeCapChoice> onChoice;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(header: true, child: Text(l10n.freeCapTitle(capMinutes), style: OmiType.title2)),
          const SizedBox(height: OmiSpacing.xs),
          Text(l10n.freeCapBody, style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4)),
          const SizedBox(height: OmiSpacing.lg),
          Container(
            key: const Key('free_cap_pro'),
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(
              color: OmiColors.surface2,
              borderRadius: OmiRadius.lgAll,
              border: Border.all(color: OmiColors.textPrimary, width: 2),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(l10n.omiProPlanName, style: OmiType.headline),
                const SizedBox(height: OmiSpacing.sm),
                for (final line in [l10n.freeCapProUnlimited, l10n.freeCapProAccuracy, l10n.freeCapProWaiting])
                  Padding(
                    padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
                    child: Row(
                      children: [
                        Icon(Icons.check, size: 16, color: OmiColors.textPrimary),
                        const SizedBox(width: OmiSpacing.sm),
                        Expanded(child: Text(line, style: OmiType.subhead)),
                      ],
                    ),
                  ),
                const SizedBox(height: OmiSpacing.sm),
                OmiButton(
                  key: const Key('free_cap_upgrade'),
                  label: l10n.upgradeToPro,
                  expand: true,
                  onPressed: () => onChoice(FreeCapChoice.upgrade),
                ),
              ],
            ),
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const Key('free_cap_phone'),
                leading: Icon(onDevicePhoneIcon),
                title: l10n.onDeviceTranscribeOnPhone,
                subtitle: l10n.freeCapPhoneSubtitle,
                onTap: () => onChoice(FreeCapChoice.transcribeOnPhone),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
