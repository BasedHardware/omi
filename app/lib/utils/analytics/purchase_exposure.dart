import 'package:omi/providers/usage_provider.dart';
import 'package:flutter/widgets.dart';

import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Emits a purchase-surface view once when it is actually mounted. Rebuilds with
/// the same mounted surface do not create additional views.
class PaywallViewedOnce extends StatefulWidget {
  const PaywallViewedOnce({
    super.key,
    required this.source,
    required this.surface,
    required this.child,
    this.currentPlan = 'unknown',
    this.catalogTier = 'not_applicable',
    this.enabled = true,
  });

  final String source;
  final PaywallViewedSurface surface;
  final String currentPlan;
  final String catalogTier;
  final bool enabled;
  final Widget child;

  @override
  State<PaywallViewedOnce> createState() => _PaywallViewedOnceState();
}

class _PaywallViewedOnceState extends State<PaywallViewedOnce> {
  bool _reported = false;
  @override
  void initState() {
    super.initState();
    _schedule();
  }

  @override
  void didUpdateWidget(covariant PaywallViewedOnce oldWidget) {
    super.didUpdateWidget(oldWidget);
    _schedule();
  }

  void _schedule() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _reported || !widget.enabled) return;
      _reported = true;
      PlatformManager.instance.analytics.paywallViewed(widget.source,
          surface: widget.surface, currentPlan: widget.currentPlan, catalogTier: widget.catalogTier);
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// Marks the useful block UI only while it is rendered. A new reason after a
/// recovery is a new presentation; ordinary parent rebuilds are deduplicated.
class AllowanceBlockShownOnce extends StatefulWidget {
  const AllowanceBlockShownOnce({
    super.key,
    required this.kind,
    required this.surface,
    required this.reason,
    required this.child,
    this.shown = true,
  });

  final String kind;
  final String surface;
  final String reason;
  final bool shown;
  final Widget child;

  @override
  State<AllowanceBlockShownOnce> createState() => _AllowanceBlockShownOnceState();
}

class _AllowanceBlockShownOnceState extends State<AllowanceBlockShownOnce> {
  String? _reported;

  String get _key => '${widget.kind}|${widget.surface}|${widget.reason}';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _sync();
    });
  }

  @override
  void didUpdateWidget(covariant AllowanceBlockShownOnce oldWidget) {
    super.didUpdateWidget(oldWidget);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _sync();
    });
  }

  void _sync() {
    if (!widget.shown) {
      _reported = null;
      return;
    }
    if (_reported == _key) return;
    _reported = _key;
    PlatformManager.instance.analytics.allowanceBlockShown(
      kind: widget.kind,
      surface: widget.surface,
      reason: widget.reason,
    );
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// Restore is the existing server subscription refresh, not a native store purchase.
Future<void> observePurchaseRestore(UsageProvider usage, String source) async {
  final analytics = PlatformManager.instance.analytics;
  analytics.restoreAttempted(source: source);
  try {
    await usage.fetchSubscription();
    analytics.restoreResult(
        source: source,
        result: usage.error != null || usage.subscription == null
            ? RestoreResultResult.failed
            : usage.subscription!.subscription.plan.isPaid
                ? RestoreResultResult.succeeded
                : RestoreResultResult.noEntitlement);
  } catch (_) {
    analytics.restoreResult(source: source, result: RestoreResultResult.failed);
    rethrow;
  }
}

/// Keeps rendering trees unchanged while attaching their presentation observer.
extension PurchaseExposureWidget on Widget {
  Widget withPurchaseExposure(
          {required String source,
          required PaywallViewedSurface surface,
          String currentPlan = 'unknown',
          String catalogTier = 'not_applicable',
          bool enabled = true}) =>
      PaywallViewedOnce(
          source: source,
          surface: surface,
          currentPlan: currentPlan,
          catalogTier: catalogTier,
          enabled: enabled,
          child: this);
  Widget withAllowanceBlock(
          {required String kind, required String surface, required String reason, bool shown = true}) =>
      AllowanceBlockShownOnce(kind: kind, surface: surface, reason: reason, shown: shown, child: this);
}
