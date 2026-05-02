import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Manual "Sync now" affordance shown on the app detail screen for installed
/// integrations. Calls [AppsProvider.syncNow] and surfaces a SnackBar with
/// the per-error-code copy below.
///
/// Visual: tonal FilledButton — `backgroundSecondary` fill, `brandPrimary`
/// label, `radiusMedium` corners, 44pt minimum touch target. Spinner
/// replaces the icon while the request is in flight.
class SyncNowButton extends StatelessWidget {
  const SyncNowButton({super.key, required this.appId});

  final String appId;

  @override
  Widget build(BuildContext context) {
    final apps = context.watch<AppsProvider>();
    final syncing = apps.isSyncing(appId);

    return SizedBox(
      width: double.infinity,
      height: AppStyles.touchTargetMinimum,
      child: FilledButton.tonal(
        onPressed: syncing ? null : () => _handleTap(context),
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.backgroundSecondary,
          foregroundColor: AppColors.brandPrimary,
          disabledBackgroundColor: AppColors.backgroundSecondary,
          disabledForegroundColor: AppColors.brandPrimary,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
            side: BorderSide(color: Colors.white.withValues(alpha: 0.06)),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (syncing)
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.brandPrimary),
              )
            else
              const Icon(Icons.sync_rounded, size: 18, color: AppColors.brandPrimary),
            const SizedBox(width: AppStyles.spacingS),
            const Text(
              'Sync now',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.brandPrimary),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleTap(BuildContext context) async {
    HapticFeedback.lightImpact();
    final apps = context.read<AppsProvider>();
    final error = await apps.syncNow(appId);
    if (!context.mounted) return;

    final messenger = ScaffoldMessenger.of(context);
    final message = _messageFor(apps, error);
    messenger.showSnackBar(SnackBar(content: Text(message), backgroundColor: AppColors.backgroundSecondary));
  }

  /// Translate the provider's error code (or null on success) into the
  /// inline copy shown to the user. Kept small and explicit — the same
  /// wording is asserted in widget tests.
  String _messageFor(AppsProvider apps, String? error) {
    if (error == null) {
      final synced = apps.lastSyncCount(appId);
      if (synced == null || synced == 0) return 'Already up to date.';
      final unit = synced == 1 ? 'item' : 'items';
      return 'Synced $synced $unit.';
    }
    switch (error) {
      case 'not_installed':
        return 'Install Jira first.';
      case 'plugin_error':
        return "Couldn't reach Jira. Try again.";
      case 'not_supported':
        return 'Sync not supported for this app.';
      case 'network':
      default:
        return 'Connection failed. Try again.';
    }
  }
}
