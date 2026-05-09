import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart' as omi;
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/logger.dart';
import 'package:superwallkit_flutter/superwallkit_flutter.dart';

/// Routes "Upgrade" / cap-hit triggers to either:
///   - the existing [PlansSheet] (legacy Stripe subscribers, who manage their
///     plan there with a Manage → customer portal button), OR
///   - the Superwall paywall registered under [placement] (everyone else —
///     non-subscribers, and users already on a Superwall mobile sub).
///
/// Per Q3=C of the rollout plan: legacy subscribers keep their existing
/// management surface, new acquisitions flow through Superwall.
///
/// Returns `true` if either surface was presented; `false` when the call
/// short-circuited (paywall hidden via `showSubscriptionUI`, or context
/// became unmounted before we could present).
Future<bool> showUpgradePaywall(
  BuildContext context, {
  required String placement,
  AnimationController? waveController,
  AnimationController? notesController,
  AnimationController? arrowController,
  Animation<double>? arrowAnimation,
}) async {
  final usage = context.read<UsageProvider>();

  // App-review / per-version subscription-UI hide flag still wins. Hidden
  // means: don't surface ANY upgrade affordance to this build.
  if (!usage.showSubscriptionUI) return false;

  if (_isLegacyStripeSubscriber(usage.subscription?.subscription)) {
    if (!context.mounted) return false;
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.black,
      builder: (sheetContext) => _LegacyPlansSheetWrapper(
        waveController: waveController,
        notesController: notesController,
        arrowController: arrowController,
        arrowAnimation: arrowAnimation,
      ),
    );
    return true;
  }

  // Non-subscriber or already on Superwall — let the SDK render the paywall.
  // The feature callback fires only when the user already has the entitlement
  // (or successfully purchases on this view); we don't need to do anything
  // there because UsageProvider re-fetches on subscription status changes.
  try {
    Superwall.shared.registerPlacement(placement, feature: () {
      Logger.debug('Superwall placement($placement) feature gate satisfied');
    });
    return true;
  } catch (e) {
    Logger.error('Superwall registerPlacement($placement) failed: $e');
    return false;
  }
}

bool _isLegacyStripeSubscriber(omi.Subscription? sub) {
  if (sub == null) return false;
  if (sub.source != omi.SubscriptionSource.stripe) return false;
  if (sub.status != omi.SubscriptionStatus.active) return false;
  // Only legacy *paid* tiers — the basic plan with source=stripe is just the
  // default for users who never bought anything.
  return sub.plan == omi.PlanType.unlimited || sub.plan == omi.PlanType.architect || sub.plan == omi.PlanType.operator;
}

/// Wraps [PlansSheet] in the animation controllers it expects. Falls back to
/// fresh local controllers when callers don't supply their own (cap-hit
/// triggers from anywhere in the app).
class _LegacyPlansSheetWrapper extends StatefulWidget {
  const _LegacyPlansSheetWrapper({
    this.waveController,
    this.notesController,
    this.arrowController,
    this.arrowAnimation,
  });

  final AnimationController? waveController;
  final AnimationController? notesController;
  final AnimationController? arrowController;
  final Animation<double>? arrowAnimation;

  @override
  State<_LegacyPlansSheetWrapper> createState() => _LegacyPlansSheetWrapperState();
}

class _LegacyPlansSheetWrapperState extends State<_LegacyPlansSheetWrapper> with TickerProviderStateMixin {
  AnimationController? _localWave;
  AnimationController? _localNotes;
  AnimationController? _localArrow;
  Animation<double>? _localArrowAnimation;

  AnimationController get _wave => widget.waveController ?? (_localWave ??= _makeRepeating(18000));
  AnimationController get _notes => widget.notesController ?? (_localNotes ??= _makeRepeating(18000));
  AnimationController get _arrow => widget.arrowController ?? (_localArrow ??= _makeRepeating(800, reverse: true));
  Animation<double> get _arrowAnim {
    final supplied = widget.arrowAnimation;
    if (supplied != null) return supplied;
    return _localArrowAnimation ??= Tween<double>(begin: 0, end: 3).animate(
      CurvedAnimation(parent: _arrow, curve: Curves.easeInOut),
    );
  }

  AnimationController _makeRepeating(int millis, {bool reverse = false}) {
    final c = AnimationController(duration: Duration(milliseconds: millis), vsync: this);
    if (reverse) {
      c.repeat(reverse: true);
    } else {
      c.repeat();
    }
    return c;
  }

  @override
  void dispose() {
    _localWave?.dispose();
    _localNotes?.dispose();
    _localArrow?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _wave,
      notesController: _notes,
      arrowController: _arrow,
      arrowAnimation: _arrowAnim,
    );
  }
}
