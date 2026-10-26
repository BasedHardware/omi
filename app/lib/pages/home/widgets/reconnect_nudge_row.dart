import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/device_last_connected.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';

/// When Home's reconnect row shows: a paired Omi has had no link for [quietFor], and the row was
/// not closed in the last [snoozeFor].
class ReconnectNudge {
  static const quietFor = Duration(days: 3);
  static const snoozeFor = Duration(hours: 24);
  static const _closedAtKey = 'reconnectNudgeDismissedAt';

  /// When the row was last closed.
  static DateTime? closedAt() => DateTime.tryParse(SharedPreferencesUtil().getString(_closedAtKey));

  static void markClosed(DateTime at) => SharedPreferencesUtil().saveString(_closedAtKey, at.toUtc().toIso8601String());

  /// Whole days without a link, or null when the row stays hidden. Only an Omi is named "Omi";
  /// any connected device hides it.
  static int? days({
    required BtDevice? paired,
    required bool connected,
    required DateTime? lastConnectedAt,
    required DateTime? dismissedAt,
    required DateTime now,
  }) {
    if (paired == null || paired.id.isEmpty || paired.type != DeviceType.omi || connected) return null;
    if (lastConnectedAt == null || now.difference(lastConnectedAt) < quietFor) return null;
    if (dismissedAt != null && now.difference(dismissedAt) < snoozeFor) return null;
    return now.difference(lastConnectedAt).inDays;
  }
}

/// A quiet row at the top of Home for an Omi that has not connected for days. Reconnect runs the
/// paired-device connect; when the Omi does not come back it opens the connection guide (a
/// Bluetooth problem shows its own prompt instead). Close hides the row for a day; a connection
/// hides it at once.
class ReconnectNudgeRow extends StatefulWidget {
  const ReconnectNudgeRow({super.key, this.now = DateTime.now, this.openGuide, this.readiness});

  final DateTime Function() now;

  /// Defaults to [ConnectionGuideSheet.show].
  final Future<void> Function(BuildContext context)? openGuide;

  /// Defaults to [BluetoothReadiness.instance].
  final BluetoothReadiness? readiness;

  @visibleForTesting
  static void resetShownForTesting() => _ReconnectNudgeRowState._shownLogged = false;

  @override
  State<ReconnectNudgeRow> createState() => _ReconnectNudgeRowState();
}

class _ReconnectNudgeRowState extends State<ReconnectNudgeRow> {
  /// Long enough for a nearby Omi to come back; after it the guide explains what to check.
  static const _connectBudget = Duration(seconds: 15);

  /// One "shown" per app run, not per rebuild.
  static bool _shownLogged = false;

  bool _closed = false;

  @override
  void initState() {
    super.initState();
    // Installs from before this row have no stamp: start their clock now rather than guess.
    if (DeviceLastConnected.read() == null && SharedPreferencesUtil().btDevice.id.isNotEmpty) {
      DeviceLastConnected.mark(widget.now());
    }
  }

  Future<void> _reconnect(int days) async {
    const TypedEvents().emit(ReconnectNudgeTapped(daysSinceConnected: days));
    OmiHaptics.selection();
    final provider = context.read<DeviceProvider>();
    try {
      await provider.scanAndConnectToDevice().timeout(_connectBudget);
    } on TimeoutException {
      // The connect keeps going natively; the row goes away if it lands.
    }
    if (!mounted || provider.connectedDevice != null) return;
    // Bluetooth off or not allowed: its own prompt already says what to do.
    if ((widget.readiness ?? BluetoothReadiness.instance).guidance != null) return;
    PlatformManager.instance.analytics.connectionGuideOpened();
    await (widget.openGuide ?? ConnectionGuideSheet.show)(context);
  }

  void _close(int days) {
    const TypedEvents().emit(ReconnectNudgeDismissed(daysSinceConnected: days));
    OmiHaptics.light();
    ReconnectNudge.markClosed(widget.now());
    setState(() => _closed = true);
  }

  @override
  Widget build(BuildContext context) {
    final (pairedDevice, connected) =
        context.select<DeviceProvider, (BtDevice?, bool)>((p) => (p.pairedDevice, p.connectedDevice != null));
    // Before a connection hydrates the provider, the stored pairing is the paired device.
    final paired = (pairedDevice?.id.isNotEmpty ?? false) ? pairedDevice! : SharedPreferencesUtil().btDevice;
    final days = _closed
        ? null
        : ReconnectNudge.days(
            paired: paired,
            connected: connected,
            lastConnectedAt: DeviceLastConnected.read(),
            dismissedAt: ReconnectNudge.closedAt(),
            now: widget.now(),
          );
    if (days == null) return const SizedBox.shrink();
    if (!_shownLogged) {
      _shownLogged = true;
      WidgetsBinding.instance
          .addPostFrameCallback((_) => const TypedEvents().emit(ReconnectNudgeShown(daysSinceConnected: days)));
    }

    final l10n = context.l10n;
    // Same frame as a conversation row: 16pt sides, 8pt above, the 36pt tile, words starting where
    // row titles start. Reconnect sits under the words and the close button on their line, so long
    // translations and large text only add lines.
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
      child: Container(
        key: const Key('reconnect_nudge_row'),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
        child: Stack(
          children: [
            Padding(
              // Less below: the compact button's touch target already extends 6pt under it.
              padding: const EdgeInsetsDirectional.fromSTEB(14, 14, OmiSpacing.xxs, OmiSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ExcludeSemantics(
                    child: Container(
                      width: 36,
                      height: 36,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                      child: Image.asset(
                        DeviceUtils.getDeviceImagePathWithState(
                          deviceType: paired.type,
                          modelNumber: paired.modelNumber,
                          deviceName: paired.name,
                          isConnected: false,
                        ),
                        width: 26,
                        height: 26,
                        fit: BoxFit.contain,
                      ),
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // A one-line status centres on the tile; only this line leaves room for close.
                        Padding(
                          padding: const EdgeInsetsDirectional.only(top: OmiSpacing.xs, end: kOmiMinTapTarget),
                          child: Text(l10n.reconnectNudgeTitle(days), style: OmiType.subhead),
                        ),
                        const SizedBox(height: 2),
                        // Wraps rather than truncates at the largest text sizes.
                        OmiButton(
                          key: const Key('reconnect_nudge_reconnect'),
                          variant: OmiButtonVariant.secondary,
                          label: l10n.reconnect,
                          size: OmiButtonSize.compact,
                          maxLines: 2,
                          onPressed: () => _reconnect(days),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            // Centred on the tile, so on the status line.
            PositionedDirectional(
              top: 10,
              end: OmiSpacing.xxs,
              child: OmiIconButton(
                key: const Key('reconnect_nudge_close'),
                icon: const Icon(Icons.close_rounded, size: 18),
                label: l10n.notNow,
                color: OmiColors.textTertiary,
                onPressed: () => _close(days),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
