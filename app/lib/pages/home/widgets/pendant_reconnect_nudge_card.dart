// Owns the EXP-005 Home card and its foreground evaluation. A foreground
// opportunity can claim the card once, only after an authenticated flag read.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/pendant_reconnect_nudge.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class PendantReconnectNudgeCard extends StatefulWidget {
  const PendantReconnectNudgeCard({
    super.key,
    required this.uid,
    required this.createdAt,
    required this.paying,
    required this.homeSelected,
    required this.pendantConnected,
    this.readFlag = PendantReconnectNudge.readFlag,
    this.emit,
    this.devicePage = const DeviceSettings(),
  });

  final String? uid;
  final DateTime? createdAt;
  final bool? paying;
  final bool homeSelected;
  final bool pendantConnected;
  final Future<bool> Function(String uid) readFlag;
  final void Function(RegisteredEvent event)? emit;
  final Widget devicePage;

  @override
  State<PendantReconnectNudgeCard> createState() => _PendantReconnectNudgeCardState();
}

class _PendantReconnectNudgeCardState extends State<PendantReconnectNudgeCard> with WidgetsBindingObserver {
  final _preferences = SharedPreferencesUtil();
  bool _scheduled = false;
  bool _evaluated = false;
  int _generation = 0;
  PendantReconnectNudgeEligible? _card;

  bool get _foreground => WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;
  bool get _homeVisible => widget.homeSelected && (ModalRoute.isCurrentOf(context) ?? true);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didUpdateWidget(PendantReconnectNudgeCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.uid != widget.uid) _resetEvaluation();
    if (!widget.homeSelected || widget.pendantConnected) _card = null;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) setState(_resetEvaluation);
  }

  void _resetEvaluation() {
    _generation++;
    _evaluated = false;
    _card = null;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  bool _canEvaluate(String uid) =>
      mounted && _foreground && _homeVisible && widget.uid == uid && _preferences.uid == uid;

  void _emit(RegisteredEvent event) => (widget.emit ?? const TypedEvents().emit)(event);

  Future<void> _evaluate(String uid) async {
    if (!_canEvaluate(uid)) return;
    _evaluated = true;
    final generation = _generation;
    bool enabled;
    try {
      enabled = await widget.readFlag(uid).timeout(const Duration(seconds: 3));
    } catch (_) {
      enabled = false;
    }
    if (!mounted || generation != _generation) return;
    if (!_canEvaluate(uid)) {
      _evaluated = false;
      return;
    }
    if (!enabled || widget.pendantConnected) return;

    final now = DateTime.now();
    final enrollment = PendantReconnectNudge.evaluate(
      enabled: enabled,
      uid: uid,
      hasPairedPendant: _preferences.btDevice.isPendant,
      now: now,
      lastConnectedAt: _preferences.lastPendantConnectedAt,
      lastShownAt: _preferences.pendantReconnectNudgeLastShownAt,
      lastDropoffSurfaceDay: _preferences.pendantDropoffSurfaceLastDay,
      lastSyncAlertAt: _preferences.lastSyncAlertTimestamp,
      createdAt: widget.createdAt,
      paying: widget.paying,
    );
    if (enrollment == null) return;
    _emit(enrollment);
    if (enrollment.arm == PendantReconnectNudgeEligibleArm.holdout) return;

    _preferences.pendantDropoffSurfaceLastDay = PendantReconnectNudge.localDay(now);
    _preferences.pendantReconnectNudgeLastShownAt = now.millisecondsSinceEpoch;
    setState(() => _card = enrollment);
    _emit(enrollment.shown);
  }

  bool _clearCard(PendantReconnectNudgeEligible card) {
    final uid = widget.uid;
    if (!identical(_card, card) || uid == null || !_canEvaluate(uid)) return false;
    setState(() => _card = null);
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final uid = widget.uid;
    if (uid != null && _foreground && _homeVisible && !_evaluated && !_scheduled) {
      _scheduled = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scheduled = false;
        if (mounted && widget.uid != null) unawaited(_evaluate(widget.uid!));
      });
    }

    final card = _card;
    if (card == null || !_homeVisible) return const SizedBox.shrink();
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.sm),
      child: DecoratedBox(
        key: const ValueKey('pendant_reconnect_nudge'),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.xs, OmiSpacing.sm),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: OmiSpacing.sm),
                    Text(l10n.pendantReconnectNudgeTitle, style: OmiType.headline),
                    const SizedBox(height: OmiSpacing.xs),
                    Text(l10n.pendantReconnectNudgeBody,
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                    const SizedBox(height: OmiSpacing.xs),
                    OmiButton(
                      key: const ValueKey('pendant_reconnect_nudge_action'),
                      label: l10n.pendantReconnectNudgeAction,
                      size: OmiButtonSize.compact,
                      maxLines: 2,
                      onPressed: () {
                        if (!_clearCard(card)) return;
                        _emit(card.tapped);
                        unawaited(routeToPage(context, widget.devicePage));
                      },
                    ),
                  ],
                ),
              ),
              IconButton(
                key: const ValueKey('pendant_reconnect_nudge_dismiss'),
                tooltip: l10n.dismiss,
                color: OmiColors.textSecondary,
                icon: const Icon(Icons.close, size: 20),
                onPressed: () {
                  if (_clearCard(card)) _emit(card.dismissed);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class HomePendantReconnectNudge extends StatelessWidget {
  const HomePendantReconnectNudge({super.key, required this.homeSelected});

  final bool homeSelected;

  @override
  Widget build(BuildContext context) {
    final (uid, createdAt) = context.select<AuthenticationProvider?, (String?, DateTime?)>((auth) {
      if (auth == null || auth.requiresReauthentication) return (null, null);
      final user = auth.user;
      if (user == null || user.isAnonymous) return (null, null);
      return (user.uid, user.metadata.creationTime);
    });
    final paying = context.select<UsageProvider?, bool?>((usage) => usage?.subscription?.subscription.plan.isPaid);
    final pendantConnected = context.select<DeviceProvider?, bool>(
      (device) => device?.isConnected == true && device?.connectedDevice?.isPendant == true,
    );
    return PendantReconnectNudgeCard(
      uid: uid,
      createdAt: createdAt,
      paying: paying,
      homeSelected: homeSelected,
      pendantConnected: pendantConnected,
    );
  }
}
