/// Fail-closed force-upgrade / migration-maintenance surface for account cutover.
/// Does not construct product children while blocked.
///
/// LIFECYCLE: permanent
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/services/account_cutover/account_cutover_gate.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AccountCutoverBlockingGate extends StatefulWidget {
  const AccountCutoverBlockingGate({
    super.key,
    this.productBuilder,
    this.child,
  }) : assert(productBuilder != null || child != null, 'productBuilder or child is required');

  /// Preferred: built only while product traffic is allowed.
  final WidgetBuilder? productBuilder;

  /// Legacy child slot; still only mounted while product traffic is allowed.
  final Widget? child;

  static final Uri _appStoreUrl = Uri.parse('https://apps.apple.com/app/id6502156163');
  static final Uri _playStoreUrl = Uri.parse('https://play.google.com/store/apps/details?id=com.friend.ios');

  @override
  State<AccountCutoverBlockingGate> createState() => _AccountCutoverBlockingGateState();
}

class _AccountCutoverBlockingGateState extends State<AccountCutoverBlockingGate> {
  // While a fence is on screen, nothing else in the app re-fetches the cutover
  // control (product traffic is blocked), so without this timer the fence
  // could only ever clear on an app lifecycle event. Poll so a fence caused by
  // a transient control-plane outage lifts on its own — and a real migration
  // fence lifts as soon as the migration completes.
  Timer? _fenceRefreshTimer;
  bool _refreshInFlight = false;

  static const _fenceRefreshInterval = Duration(seconds: 30);

  void _syncFenceRefreshTimer(bool fenceVisible) {
    if (fenceVisible && _fenceRefreshTimer == null) {
      _fenceRefreshTimer = Timer.periodic(_fenceRefreshInterval, (_) async {
        if (_refreshInFlight) return;
        _refreshInFlight = true;
        try {
          await AccountCutoverRuntime.instance.refresh();
        } finally {
          _refreshInFlight = false;
        }
      });
    } else if (!fenceVisible && _fenceRefreshTimer != null) {
      _fenceRefreshTimer!.cancel();
      _fenceRefreshTimer = null;
    }
  }

  @override
  void dispose() {
    _fenceRefreshTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AccountCutoverRuntime.instance,
      builder: (context, _) {
        final runtime = AccountCutoverRuntime.instance;
        final decision = runtime.decision;
        final fenceVisible = decision != AccountCutoverGateDecision.allowProductTraffic;
        _syncFenceRefreshTimer(fenceVisible);
        if (!fenceVisible) {
          return widget.productBuilder?.call(context) ?? widget.child!;
        }

        return AccountCutoverBlockingView(
          decision: decision,
          strandedNewData: runtime.control.strandedNewData,
          appStoreUrl: AccountCutoverBlockingGate._appStoreUrl,
          playStoreUrl: AccountCutoverBlockingGate._playStoreUrl,
          // A fence this client synthesized after the server had allowed the
          // owner (unreachable control plane, a blown refresh) keeps a manual
          // way back to that last authoritative projection. A fence the server
          // itself decided — or one with no server allow to return to — does
          // not.
          onSkipUnresolvedFence: runtime.canSkipUnresolvedFence ? runtime.skipUnresolvedFence : null,
        );
      },
    );
  }
}

class AccountCutoverBlockingView extends StatelessWidget {
  const AccountCutoverBlockingView({
    super.key,
    required this.decision,
    required this.strandedNewData,
    required this.appStoreUrl,
    required this.playStoreUrl,
    this.onSkipUnresolvedFence,
  });

  final AccountCutoverGateDecision decision;
  final bool strandedNewData;
  final Uri appStoreUrl;
  final Uri playStoreUrl;

  /// Non-null only while this client synthesized the fence and the server had
  /// authoritatively allowed the owner. Pressing it returns to that last
  /// authoritative projection for this session.
  final VoidCallback? onSkipUnresolvedFence;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final forceUpgrade = decision == AccountCutoverGateDecision.forceUpgrade;
    final title = forceUpgrade ? l10n.accountCutoverUpdateRequiredTitle : l10n.accountCutoverMigrationInProgressTitle;
    final message = forceUpgrade
        ? l10n.accountCutoverUpdateRequiredMessage
        : (strandedNewData
            ? l10n.accountCutoverMigrationRollbackMessage
            : l10n.accountCutoverMigrationInProgressMessage);

    return Semantics(
      container: true,
      explicitChildNodes: true,
      label: '$title. $message',
      child: Material(
        color: Colors.black,
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 360),
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      forceUpgrade ? Icons.system_update : Icons.hourglass_top,
                      color: Colors.white,
                      size: 36,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      title,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      message,
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.72), fontSize: 15, height: 1.35),
                    ),
                    if (forceUpgrade) ...[
                      const SizedBox(height: 20),
                      FilledButton(
                        onPressed: () async {
                          final url = Platform.isIOS ? appStoreUrl : playStoreUrl;
                          await launchUrl(url, mode: LaunchMode.externalApplication);
                        },
                        child: Text(l10n.accountCutoverOpenStore),
                      ),
                    ] else if (onSkipUnresolvedFence != null) ...[
                      const SizedBox(height: 20),
                      TextButton(
                        onPressed: onSkipUnresolvedFence,
                        child: Text(l10n.skip, style: const TextStyle(color: Colors.white70)),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
