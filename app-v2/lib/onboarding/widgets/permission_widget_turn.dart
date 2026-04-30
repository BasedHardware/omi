import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

enum PermissionKind { microphone, notifications, backgroundActivity, location }

class PermissionWidgetTurn extends StatefulWidget {
  final String turnId;
  final PermissionKind kind;
  const PermissionWidgetTurn({super.key, required this.turnId, required this.kind});

  @override
  State<PermissionWidgetTurn> createState() => _PermissionWidgetTurnState();
}

class _PermissionWidgetTurnState extends State<PermissionWidgetTurn> {
  PermissionStatus? _status;
  bool _busy = false;

  Permission get _permission {
    switch (widget.kind) {
      case PermissionKind.microphone:
        return Permission.microphone;
      case PermissionKind.notifications:
        return Permission.notification;
      case PermissionKind.backgroundActivity:
        return Permission.ignoreBatteryOptimizations;
      case PermissionKind.location:
        return Permission.locationWhenInUse;
    }
  }

  String _label(AppLocalizations l) {
    switch (widget.kind) {
      case PermissionKind.microphone:
        return l.onboardingPermissionLabelMicrophone;
      case PermissionKind.notifications:
        return l.onboardingPermissionLabelNotifications;
      case PermissionKind.backgroundActivity:
        return l.onboardingPermissionLabelBackground;
      case PermissionKind.location:
        return l.onboardingPermissionLabelLocation;
    }
  }

  String _helper(AppLocalizations l) {
    switch (widget.kind) {
      case PermissionKind.microphone:
        return l.onboardingPermissionLabelMicrophoneHelper;
      case PermissionKind.notifications:
        return l.onboardingPermissionLabelNotificationsHelper;
      case PermissionKind.backgroundActivity:
        return l.onboardingPermissionLabelBackgroundHelper;
      case PermissionKind.location:
        return l.onboardingPermissionLabelLocationHelper;
    }
  }

  Future<void> _request() async {
    setState(() => _busy = true);
    // If the OS already permanently denied this permission, request() returns
    // immediately with the same status — no dialog appears. Surface that
    // explicitly so the user can open Settings instead of seeing a silent
    // "Denied" land in the chat right after they tapped Allow.
    final initial = await _permission.status;
    if (initial.isPermanentlyDenied) {
      if (!mounted) return;
      setState(() {
        _status = initial;
        _busy = false;
      });
      return;
    }

    final result = await _permission.request();
    if (!mounted) return;
    setState(() {
      _status = result;
      _busy = false;
    });

    if (result.isGranted || result.isLimited) {
      context.read<OnboardingChatProvider>().reportWidgetCapture(context, widget.turnId, 'granted');
    }
    // For denied/permanentlyDenied: leave the card open so the user can
    // retry, open Settings, or skip.
  }

  Future<void> _openSettings() async {
    await openAppSettings();
  }

  void _continueDenied() {
    context.read<OnboardingChatProvider>().reportWidgetCapture(context, widget.turnId, 'denied');
  }

  void _skip() {
    context.read<OnboardingChatProvider>().skipCurrent(context);
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isGranted = _status?.isGranted == true || _status?.isLimited == true;
    final isBlocked = _status?.isPermanentlyDenied == true;
    final canSkip = context.read<OnboardingChatProvider>().canSkip;

    return Container(
      margin: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      padding: const EdgeInsets.all(AppStyles.spacingL),
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  _label(l),
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                ),
              ),
              if (_status != null) _StatusBadge(status: _status!),
            ],
          ),
          const SizedBox(height: 6),
          Text(_helper(l), style: const TextStyle(fontSize: 13, color: AppColors.textTertiary)),
          if (isBlocked) ...[
            const SizedBox(height: AppStyles.spacingS),
            Text(
              'iOS is blocking this permission. Open Settings to allow it, or continue without.',
              style: TextStyle(fontSize: 12, color: AppColors.errorColor.withValues(alpha: 0.9)),
            ),
          ],
          const SizedBox(height: AppStyles.spacingL),
          Row(
            children: [
              Expanded(
                child: ElevatedButton(
                  onPressed: _busy || isGranted ? null : (isBlocked ? _openSettings : _request),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.brandPrimary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppStyles.radiusPill)),
                  ),
                  child: Text(_busy ? '…' : (isBlocked ? 'Open Settings' : l.onboardingPermissionAllow)),
                ),
              ),
              if (isBlocked) ...[
                const SizedBox(width: 12),
                TextButton(
                  onPressed: _continueDenied,
                  child: const Text('Continue', style: TextStyle(color: AppColors.textTertiary, fontWeight: FontWeight.w500)),
                ),
              ] else if (canSkip) ...[
                const SizedBox(width: 12),
                TextButton(
                  onPressed: _skip,
                  child: Text(l.onboardingChipSkipForNow,
                      style: const TextStyle(color: AppColors.textTertiary, fontWeight: FontWeight.w500)),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final PermissionStatus status;
  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    String label;
    Color bg;
    Color fg;
    if (status.isGranted || status.isLimited) {
      label = l.onboardingPermissionGranted;
      bg = AppColors.successColor.withValues(alpha: 0.18);
      fg = AppColors.successColor;
    } else if (status.isDenied || status.isPermanentlyDenied) {
      label = l.onboardingPermissionDenied;
      bg = AppColors.errorColor.withValues(alpha: 0.18);
      fg = AppColors.errorColor;
    } else {
      label = l.onboardingPermissionPending;
      bg = AppColors.backgroundQuaternary;
      fg = AppColors.textTertiary;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(AppStyles.radiusPill)),
      child: Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: fg)),
    );
  }
}
