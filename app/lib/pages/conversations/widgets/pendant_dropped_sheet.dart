import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/device_tile.dart';

/// Opened by tapping a Disconnected capture card: what happened, the pendant and what it is doing
/// now, then the two things to know. Got It closes it; Device Settings opens the pendant's page.
Future<void> showPendantDroppedSheet(BuildContext context, {required String source, Duration? elapsed}) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.disconnected,
    builder: (sheetContext) => PendantDroppedSheet(
      source: source,
      elapsed: elapsed,
      onDeviceSettings: () {
        Navigator.pop(sheetContext);
        if (context.mounted) routeToPage(context, const ConnectedDevice());
      },
    ),
  );
}

class PendantDroppedSheet extends StatelessWidget {
  const PendantDroppedSheet({super.key, required this.source, this.elapsed, required this.onDeviceSettings});

  /// The capture source that dropped ('omi', 'limitless', …).
  final String source;

  /// How long it had recorded when it dropped.
  final Duration? elapsed;

  final VoidCallback onDeviceSettings;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // Follows the pendant while the sheet is open: Reconnecting… with a spinner while a reconnect runs.
    final (name, reconnecting) = context.select<DeviceProvider, (String?, bool)>(
      (d) => (d.pairedDevice?.name, d.isConnecting),
    );
    final status = [
      if (elapsed != null) LiveCaptureCard.formatElapsed(elapsed!),
      reconnecting ? l10n.reconnecting : l10n.disconnected,
    ].join('  ·  ');
    final secondary = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.pendantLostConnection,
              textAlign: TextAlign.center, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.md),
          Container(
            key: const ValueKey('pendant_dropped_status'),
            padding: const EdgeInsets.all(OmiSpacing.sm),
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
            child: Row(children: [
              DeviceTile(source: source),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(name ?? CaptureSources.label(context, source),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                  Text(status, style: secondary.copyWith(fontFeatures: const [FontFeature.tabularFigures()])),
                ]),
              ),
              if (reconnecting) const OmiSpinner(size: OmiSpinnerSize.small),
            ]),
          ),
          const SizedBox(height: OmiSpacing.xs),
          _Point(icon: Icons.verified_user_outlined, text: l10n.pendantRecordingSafe),
          _Point(icon: Icons.sync_rounded, text: l10n.pendantReconnectsOnItsOwn),
          const SizedBox(height: OmiSpacing.md),
          OmiButton(label: l10n.gotIt, onPressed: () => Navigator.pop(context)),
          OmiButton.tertiary(label: l10n.deviceSettings, onPressed: onDeviceSettings),
        ],
      ),
    );
  }
}

/// One thing to know: a quiet glyph in the tile's column, then the sentence.
class _Point extends StatelessWidget {
  const _Point({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
      child: Row(children: [
        SizedBox(
          width: DeviceTile.size,
          child: ExcludeSemantics(child: Icon(icon, size: 20, color: OmiColors.textSecondary)),
        ),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(child: Text(text, style: OmiType.subhead)),
      ]),
    );
  }
}
