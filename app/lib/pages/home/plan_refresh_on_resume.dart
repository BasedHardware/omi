import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/usage_provider.dart';

/// Re-reads the plan when the app returns to the foreground, because it may have changed in
/// Google Play or the Stripe portal while the app was away. [UsageProvider.refreshOnResume] owns the
/// throttle and the signed-out and purchase-in-flight guards; this only forwards the lifecycle.
class PlanRefreshOnResume extends StatefulWidget {
  const PlanRefreshOnResume({super.key, required this.child, this.isSignedIn});

  final Widget child;

  /// Test seam; defaults to [AuthenticationProvider.isSignedIn].
  final bool Function(BuildContext context)? isSignedIn;

  @override
  State<PlanRefreshOnResume> createState() => _PlanRefreshOnResumeState();
}

class _PlanRefreshOnResumeState extends State<PlanRefreshOnResume> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !mounted) return;
    final signedIn = widget.isSignedIn?.call(context) ?? context.read<AuthenticationProvider>().isSignedIn();
    unawaited(context.read<UsageProvider>().refreshOnResume(signedIn: signedIn));
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
