import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/yearly_switch_retention.dart' as api;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/pages/settings/widgets/yearly_switch.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Each mounted host attempts once. The server's UID enrollment owns admission
/// across hosts, devices, reinstalls and retries; no client preference is truth.
class YearlyRetentionPlacement extends StatefulWidget {
  const YearlyRetentionPlacement(
      {super.key,
      required this.surface,
      this.emphasized = false,
      this.busy = false,
      this.onSwitched,
      this.claim,
      this.readEnabled,
      this.loadPreview,
      this.apply});

  final YearlySwitchSurface surface;
  final bool emphasized;
  final bool busy;
  final VoidCallback? onSwitched;
  final Future<wire.GeneratedYearlySwitchResponse?> Function(String)? claim;
  final Future<bool> Function()? readEnabled;
  final YearlySwitchLoader? loadPreview;
  final YearlySwitchApplier? apply;

  @override
  State<YearlyRetentionPlacement> createState() => _YearlyRetentionPlacementState();
}

class _YearlyRetentionPlacementState extends State<YearlyRetentionPlacement> with WidgetsBindingObserver {
  wire.GeneratedYearlySwitchResponse? _offer;
  String? _attemptedFor;
  Timer? _refresh;
  bool _opening = false;

  String? get _candidate {
    final candidate = yearlySwitchCandidate(context.read<UsageProvider?>());
    return candidate == null ? null : '${SharedPreferencesUtil().uid}:$candidate';
  }

  @override
  void initState() {
    super.initState();
    assert(widget.surface != YearlySwitchSurface.plans);
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    _refresh?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _offer != null) unawaited(_checkEnabled());
  }

  Future<bool> _checkEnabled() async {
    bool enabled;
    try {
      if (widget.readEnabled != null) {
        enabled = await widget.readEnabled!().timeout(const Duration(seconds: 3));
      } else {
        final status = await api.yearlyRetentionStatus().timeout(const Duration(seconds: 3));
        enabled = status is ApiSuccess<bool> && status.data;
      }
    } catch (_) {
      enabled = false;
    }
    if (!mounted) return false;
    if (!enabled || _candidate != _attemptedFor) {
      _refresh?.cancel();
      setState(() => _offer = null);
      return false;
    }
    return true;
  }

  Future<void> _claim(String candidate) async {
    wire.GeneratedYearlySwitchResponse? offer;
    try {
      if (widget.claim != null) {
        offer = await widget.claim!(widget.surface.name).timeout(const Duration(seconds: 4));
      } else {
        final result = await api.claimYearlyRetention(widget.surface.name).timeout(const Duration(seconds: 4));
        if (result is ApiSuccess<wire.GeneratedYearlySwitchResponse>) offer = result.data;
      }
    } catch (_) {
      return;
    }
    if (!mounted ||
        _candidate != candidate ||
        offer?.eligible != true ||
        offer?.yearlyAmount == null ||
        offer?.savingsAmount == null ||
        offer?.planId == null) {
      return;
    }
    if (!await _checkEnabled() || !mounted || _candidate != candidate || _attemptedFor != candidate) return;
    setState(() => _offer = offer);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _candidate == candidate && identical(_offer, offer)) {
        observeYearlyRetention(widget.surface, YearlyRetentionObservationAction.shown);
      }
    });
    _refresh = Timer.periodic(const Duration(seconds: 30), (_) => unawaited(_checkEnabled()));
  }

  Future<void> _open() async {
    if (_opening || widget.busy) return;
    _opening = true;
    final candidate = _candidate;
    try {
      if (!await _checkEnabled() || !mounted || _candidate != candidate) return;
      final switched = await showYearlySwitchSheet(context,
          surface: widget.surface, load: widget.loadPreview, apply: widget.apply, readEnabled: widget.readEnabled);
      if (!mounted) return;
      if (switched) {
        _refresh?.cancel();
        setState(() => _offer = null);
        widget.onSwitched?.call();
      }
    } finally {
      _opening = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final subscription = context.watch<UsageProvider?>();
    final candidate = yearlySwitchCandidate(subscription) == null ? null : _candidate;
    if (candidate == null) return const SizedBox.shrink();
    if (_attemptedFor != candidate) {
      _attemptedFor = candidate;
      _offer = null;
      _refresh?.cancel();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _candidate == candidate) unawaited(_claim(candidate));
      });
    }
    final offer = _offer;
    if (offer == null) return const SizedBox.shrink();
    final l10n = context.l10n;
    final plan = planTitleForTier(offer.planId!, subscription?.subscription?.availablePlans ?? []);
    if (plan == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.sm),
      child: YearlySwitchRow(
        key: ValueKey('yearly_retention_${widget.surface.name}'),
        title: widget.emphasized || widget.surface == YearlySwitchSurface.engaged
            ? l10n.yearlySwitchHomeTitle(yearlySwitchMoney(offer.savingsAmount!, offer.currency))
            : l10n.yearlySwitchTitle,
        subtitle:
            '${l10n.yearlySwitchPlanValue(plan, yearlySwitchMoney(offer.yearlyAmount!, offer.currency))}\n${l10n.yearlySwitchHomeSubtitle}',
        color: widget.emphasized ? OmiColors.surface3 : OmiColors.surface2,
        tileColor: OmiColors.surface1,
        onTap: widget.busy ? () {} : _open,
        onDismiss: widget.surface == YearlySwitchSurface.engaged
            ? () {
                _refresh?.cancel();
                observeYearlyRetention(widget.surface, YearlyRetentionObservationAction.dismissed);
                setState(() => _offer = null);
              }
            : null,
      ),
    );
  }
}
