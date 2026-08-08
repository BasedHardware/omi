/// Smallest honest blocking overlay for account cutover force-upgrade /
/// migration-maintenance. Reuses existing store URLs; does not invent a new
/// update-policy backend.
///
/// LIFECYCLE: permanent
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/services/account_cutover/account_cutover_gate.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';

class AccountCutoverBlockingGate extends StatelessWidget {
  const AccountCutoverBlockingGate({super.key, required this.child});

  final Widget child;

  static final Uri _appStoreUrl = Uri.parse('https://apps.apple.com/app/id6502156163');
  static final Uri _playStoreUrl = Uri.parse('https://play.google.com/store/apps/details?id=com.friend.ios');

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AccountCutoverRuntime.instance,
      builder: (context, _) {
        final runtime = AccountCutoverRuntime.instance;
        final decision = runtime.decision;
        if (decision == AccountCutoverGateDecision.allowProductTraffic) {
          return child;
        }

        final forceUpgrade = decision == AccountCutoverGateDecision.forceUpgrade;
        final title = forceUpgrade ? 'Update Required' : 'Migration in Progress';
        final message = forceUpgrade
            ? 'Install the latest Omi app to continue after account migration.'
            : (runtime.control.strandedNewData
                ? 'Your account is in maintenance after a migration rollback. Some newer data may be stranded.'
                : 'Your account is migrating. Product features are paused until migration finishes.');

        return Stack(
          fit: StackFit.expand,
          children: [
            child,
            Material(
              color: Colors.black.withValues(alpha: 0.86),
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
                                final url = Platform.isIOS ? _appStoreUrl : _playStoreUrl;
                                await launchUrl(url, mode: LaunchMode.externalApplication);
                              },
                              child: const Text('Open store'),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
