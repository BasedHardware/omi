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

  /// The next moment [days] changes with time alone: the row appearing, a close running out, or
  /// the count going up a day. Null when only a device event can change it.
  static DateTime? nextChange({
    required BtDevice? paired,
    required bool connected,
    required DateTime? lastConnectedAt,
    required DateTime? dismissedAt,
    required DateTime now,
  }) {
    if (paired == null || paired.id.isEmpty || paired.type != DeviceType.omi || connected) return null;
    if (lastConnectedAt == null) return null;
    final candidates = [
      lastConnectedAt.add(quietFor),
      if (dismissedAt != null) dismissedAt.add(snoozeFor),
      lastConnectedAt.add(Duration(days: now.difference(lastConnectedAt).inDays + 1)),
    ].where((at) => at.isAfter(now));
    return candidates.isEmpty ? null : candidates.reduce((a, b) => a.isBefore(b) ? a : b);
  }
}

/// A quiet row at the top of Home for an Omi that has not connected for days. Reconnect first
/// checks Bluetooth (off or not allowed: the app's Bluetooth prompt, nothing else), then runs the
/// paired-device connect; when the Omi does not come back it opens the connection guide, if that
/// attempt still stands and Home is still in front. Close hides the row for a day; a connection
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

class _ReconnectNudgeRowState extends State<ReconnectNudgeRow> with WidgetsBindingObserver {
  /// Long enough for a nearby Omi to come back; after it the guide explains what to check.
  static const _connectBudget = Duration(seconds: 15);

  /// One "shown" per app run, not per rebuild.
  static bool _shownLogged = false;

  /// The Reconnect attempt that may still open the guide. A newer tap or a close invalidates it.
  int _attempt = 0;

  /// Re-evaluates when time alone changes the row (Home stays mounted for days).
  Timer? _boundary;
  DateTime? _boundaryAt;

  BluetoothReadiness get _readiness => widget.readiness ?? BluetoothReadiness.instance;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Installs from before this row have no stamp: start their clock now rather than guess.
    if (DeviceLastConnected.read() == null && SharedPreferencesUtil().btDevice.id.isNotEmpty) {
      DeviceLastConnected.mark(widget.now());
    }
  }

  @override
  void dispose() {
    _boundary?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Timers do not run while the app is suspended: look again on the way back.
    if (state == AppLifecycleState.resumed && mounted) {
      _boundaryAt = null;
      setState(() {});
    }
  }

  void _scheduleBoundary(DateTime? at) {
    if (at == _boundaryAt) return;
    _boundary?.cancel();
    _boundaryAt = at;
    if (at == null) return;
    final wait = at.difference(widget.now());
    _boundary = Timer(wait.isNegative ? Duration.zero : wait, () {
      _boundaryAt = null;
      if (mounted) setState(() {});
    });
  }

  /// Home's tab is showing, nothing is pushed over it, and the app is in the foreground.
  bool get _homeInFront {
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    return (lifecycle == null || lifecycle == AppLifecycleState.resumed) &&
        (ModalRoute.of(context)?.isCurrent ?? true) &&
        TickerMode.valuesOf(context).enabled;
  }

  Future<void> _reconnect(int days) async {
    const TypedEvents().emit(ReconnectNudgeTapped(daysSinceConnected: days));
    OmiHaptics.selection();
    final attempt = ++_attempt;
    // Bluetooth off or not allowed: the app's Bluetooth prompt is the fix, even if it was dismissed
    // before. No connect and no device guide.
    if (!await _readiness.ensureReadyForUser(BluetoothUse.connection)) return;
    if (!mounted || attempt != _attempt) return;
    final provider = context.read<DeviceProvider>();
    try {
      await provider.scanAndConnectToDevice().timeout(_connectBudget);
    } on TimeoutException {
      // The connect keeps going natively; the row goes away if it lands.
    }
    if (!mounted || attempt != _attempt || provider.connectedDevice != null || !_homeInFront) return;
    PlatformManager.instance.analytics.connectionGuideOpened();
    unawaited((widget.openGuide ?? ConnectionGuideSheet.show)(context));
  }

  void _close(int days) {
    const TypedEvents().emit(ReconnectNudgeDismissed(daysSinceConnected: days));
    OmiHaptics.light();
    _attempt++;
    ReconnectNudge.markClosed(widget.now());
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final (pairedDevice, connected) =
        context.select<DeviceProvider, (BtDevice?, bool)>((p) => (p.pairedDevice, p.connectedDevice != null));
    // Before a connection hydrates the provider, the stored pairing is the paired device.
    final paired = (pairedDevice?.id.isNotEmpty ?? false) ? pairedDevice! : SharedPreferencesUtil().btDevice;
    final lastConnectedAt = DeviceLastConnected.read();
    final closedAt = ReconnectNudge.closedAt();
    final now = widget.now();
    _scheduleBoundary(ReconnectNudge.nextChange(
        paired: paired, connected: connected, lastConnectedAt: lastConnectedAt, dismissedAt: closedAt, now: now));
    final days = ReconnectNudge.days(
        paired: paired, connected: connected, lastConnectedAt: lastConnectedAt, dismissedAt: closedAt, now: now);
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
